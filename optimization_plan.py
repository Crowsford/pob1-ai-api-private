
# PoE BuildLab AI — Reusable Optimization Planner
# Reads current Pareto snapshot, discovers next cycle,
# validates provenance, and creates profile batches.
# Default mode: DRY RUN. No PoB calls.

import hashlib
import re
from pathlib import Path

from build_constraints import evaluate_constraints
from experiment_storage import get_experiment_dir, load_report
from profile_experiment_storage import (
    load_profile_report,
    report_path,
    save_profile_report,
)
from profile_scheduler_v18 import (
    candidate_row,
    historical_state,
    metric_point,
    rank_candidate,
    select_diverse,
)

POOL = "multi_swap_candidate_pool_fullstats_v16.json"
BATCH_PREFIX = "profile_batch_cycle_"
RESULT_PREFIX = "profile_executed_cycle_"


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def completed(report):
    return (
        report.get("results", [])
        + report.get("invalidTrees", [])
        + report.get("invalidCandidates", [])
    )


def cycle_ids(profile):
    folder = report_path(
        profile, "placeholder.json"
    ).parent

    found = set()

    for path in folder.glob(BATCH_PREFIX + "*.json"):
        match = re.fullmatch(
            r"profile_batch_cycle_(\d{4,})\.json",
            path.name,
        )
        if match is None:
            raise RuntimeError(
                f"Unexpected cycle filename: {path.name}"
            )
        found.add(match.group(1))

    return found


def verify_snapshot(profile, other, directory,
                    cache_name, fingerprint, cycle_id):
    name = f"merged_frontier_cycle_{cycle_id}.json"
    snapshot = load_profile_report(profile, name)

    if snapshot.get("version") != "cycle-refresh-1":
        raise RuntimeError("Unsupported frontier snapshot")

    if snapshot.get("cycleId") != cycle_id:
        raise RuntimeError("Snapshot cycle mismatch")

    if snapshot.get("engineFingerprint") != fingerprint:
        raise RuntimeError("Snapshot engine mismatch")

    sources = snapshot["sourceHashes"]

    if "cache/" + cache_name not in sources:
        raise RuntimeError("Snapshot has no shared cache")

    for source_name, expected in sources.items():
        if source_name.startswith("cache/"):
            path = directory / source_name[len("cache/"):]
        elif source_name.startswith("legacy/"):
            path = directory / source_name[len("legacy/"):]
        elif source_name.startswith("profile/"):
            path = report_path(
                profile, source_name[len("profile/"):]
            )
        elif source_name.startswith("otherProfile/"):
            path = report_path(
                other, source_name[len("otherProfile/"):]
            )
        else:
            raise RuntimeError(
                f"Unknown source type: {source_name}"
            )

        if file_hash(path) != expected:
            raise RuntimeError(
                f"Stale frontier source: {source_name}"
            )

    return snapshot, name


def verify_cycles(profile, ids, cache_keys):
    observed = set()

    for cycle_id in sorted(ids):
        batch_name = (
            f"{BATCH_PREFIX}{cycle_id}.json"
        )
        result_name = (
            f"{RESULT_PREFIX}{cycle_id}.json"
        )

        batch = load_profile_report(profile, batch_name)
        result = load_profile_report(profile, result_name)

        batch_path = report_path(profile, batch_name)

        if batch.get("batchId") != cycle_id:
            raise RuntimeError(
                f"Batch identity mismatch: {cycle_id}"
            )

        if result.get("batchSha256") != file_hash(batch_path):
            raise RuntimeError(
                f"Batch hash mismatch: {cycle_id}"
            )

        planned = [c["key"] for c in batch["candidates"]]
        finished = [r["key"] for r in completed(result)]

        if (
            len(planned) != batch["planned"]
            or len(planned) != len(set(planned))
            or len(finished) != len(set(finished))
            or set(planned) != set(finished)
        ):
            raise RuntimeError(
                f"Unfinished or corrupt cycle: {cycle_id}"
            )

        if set(finished) - cache_keys:
            raise RuntimeError(
                f"Cycle missing from cache: {cycle_id}"
            )

        if observed & set(finished):
            raise RuntimeError(
                f"Duplicate calculated cycle keys: {cycle_id}"
            )

        observed.update(finished)

    return observed


def build_batch(profile, snapshot, snapshot_name,
                pool, baseline, done, conflicts,
                fingerprint, next_id, size):
    passing = []
    rejected = []

    points = [
        metric_point(row["changes"])
        for row in snapshot["frontier"]
    ]

    for candidate in pool["candidates"]:
        key = candidate["key"]

        if key in done:
            continue

        removal = tuple(sorted(candidate["removeIds"]))

        if removal in conflicts:
            continue

        checked = evaluate_constraints(
            baseline,
            candidate_row(candidate),
            limits=profile["constraints"],
        )

        score, pareto_candidate = rank_candidate(
            candidate, checked, points
        )

        row = dict(candidate)
        row["legacyPredictedStatus"] = candidate[
            "predictedStatus"
        ]
        row["predictedStatus"] = checked["status"]
        row["predictedProblems"] = checked["problems"]

        for field, key_name in (
            ("predictedDpsPercent", "dps_percent"),
            ("predictedEhpPercent", "ehp_percent"),
            ("predictedManaRegenPercent", "mana_regen_percent"),
        ):
            row[field] = round(
                checked["changes"][key_name], 6
            )

        row["profileRankingScore"] = round(score, 6)
        row["paretoCandidate"] = pareto_candidate

        if checked["status"] == "PASS":
            passing.append(row)
        elif (
            len(checked["problems"]) <= 2
            and checked["changes"]["dps_percent"] >= 0
        ):
            rejected.append(row)

    for rows in (passing, rejected):
        rows.sort(
            key=lambda x: (
                -x["profileRankingScore"],
                x["key"],
            )
        )

    reject_target = max(1, size // 5) if size >= 5 else 0
    pass_target = size - reject_target

    used = set()
    selected = select_diverse(passing, pass_target, used)
    selected += select_diverse(rejected, reject_target, used)

    if len(selected) < size:
        selected_keys = {r["key"] for r in selected}
        remaining = [
            r for r in passing + rejected
            if r["key"] not in selected_keys
        ]
        selected.extend(remaining[:size - len(selected)])

    selected_keys = [r["key"] for r in selected]

    if len(selected_keys) != len(set(selected_keys)):
        raise RuntimeError("Duplicate selected candidates")

    if set(selected_keys) & done:
        raise RuntimeError("Completed candidate selected again")

    if any(
        tuple(sorted(r["removeIds"])) in conflicts
        for r in selected
    ):
        raise RuntimeError("Known tree conflict selected")

    return {
        "version": "2.4",
        "batchId": next_id,
        "engineFingerprint": fingerprint,
        "frontierFile": snapshot_name,
        "frontierSha256": file_hash(
            report_path(profile, snapshot_name)
        ),
        "poolFile": POOL,
        "poolSha256": file_hash(
            get_experiment_dir(
                profile["build"]["xmlPath"],
                profile["build"]["skillGroup"],
            ) / POOL
        ),
        "completedUniqueAttempts": len(done),
        "knownRemovalConflicts": len(conflicts),
        "availablePredictedPass": len(passing),
        "availableExploratoryReject": len(rejected),
        "planned": len(selected),
        "candidates": selected,
    }


def plan(normal, strict, engine, fingerprint,
         size=10, write=False):
    if size < 1:
        raise ValueError("Batch size must be positive")

    profiles = (normal, strict)

    xml = normal["build"]["xmlPath"]
    group = normal["build"]["skillGroup"]

    if (
        strict["build"]["xmlPath"] != xml
        or strict["build"]["skillGroup"] != group
    ):
        raise RuntimeError("Profiles use different builds")

    directory = get_experiment_dir(xml, group)

    cache_name = (
        f"pob_measurements_v19_{fingerprint[:16]}.json"
    )

    cache = load_report(
        directory / cache_name, xml, group
    )

    if (
        cache.get("version") != "1.9"
        or cache.get("engineFingerprint") != fingerprint
        or cache.get("engine") != engine
    ):
        raise RuntimeError("Shared cache identity mismatch")

    cache_keys = set(cache["measurements"])

    first_ids = cycle_ids(normal)
    second_ids = cycle_ids(strict)

    if first_ids != second_ids or not first_ids:
        raise RuntimeError(
            "Profiles have inconsistent cycle histories"
        )

    latest = max(first_ids, key=int)

    if int(latest) == 9999:
        raise RuntimeError("Cycle numbering exhausted")

    next_id = f"{int(latest) + 1:04d}"

    legacy_done, conflicts = historical_state(
        directory, xml, group
    )

    if legacy_done & cache_keys:
        raise RuntimeError("Legacy/cache overlap")

    done = legacy_done | cache_keys

    pool = load_report(directory / POOL, xml, group)

    if pool.get("version") != "1.2-pool":
        raise RuntimeError("Unexpected pool format")

    baseline = load_report(
        directory / "swap_executed.json", xml, group
    )["baseline"]

    prepared = []

    for profile, other in (
        (normal, strict),
        (strict, normal),
    ):
        verified_cycles = verify_cycles(
            profile, first_ids, cache_keys
        )

        if not verified_cycles.issubset(cache_keys):
            raise RuntimeError("Uncached completed cycles")

        snapshot, snapshot_name = verify_snapshot(
            profile, other, directory,
            cache_name, fingerprint, latest,
        )

        if snapshot["sharedMeasurements"] != len(cache_keys):
            raise RuntimeError("Frontier cache count mismatch")

        if snapshot["completedUniqueAttempts"] != len(done):
            raise RuntimeError("Frontier history count mismatch")

        report = build_batch(
            profile, snapshot, snapshot_name,
            pool, baseline, done, conflicts,
            fingerprint, next_id, size,
        )

        output_name = (
            f"{BATCH_PREFIX}{next_id}.json"
        )

        output_path = report_path(profile, output_name)

        if output_path.exists():
            raise RuntimeError(
                f"Next batch already exists: {output_path}"
            )

        prepared.append(
            (profile, output_name, report)
        )

    print("=== OPTIMIZATION PLAN ===")
    print("Previous cycle:", latest)
    print("Next cycle:", next_id)
    print("Completed unique attempts:", len(done))
    print("Shared cache entries:", len(cache_keys))

    for profile, name, report in prepared:
        print("\nPROFILE:", profile["build"]["name"])
        print("Selected:", report["planned"])

        for row in report["candidates"]:
            print(
                row["key"],
                row["predictedStatus"],
                "DPS:",
                row["predictedDpsPercent"],
            )

    if not write:
        print("\nDRY RUN: no files modified")
        print("Use --write to save both batches")
        return

    for profile, name, report in prepared:
        path = save_profile_report(
            profile, name, report
        )
        print("Saved:", path)

    print("\nPlanning completed. PoB calls: 0")
