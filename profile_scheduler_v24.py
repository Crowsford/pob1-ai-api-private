
# PoE BuildLab AI — Profile Scheduler v2.4
# Profile-aware ranking with shared-cache exclusions.
# No PoB calls. Legacy reports untouched.

import argparse
from collections import Counter
from copy import deepcopy
from pathlib import Path

from build_constraints import evaluate_constraints
from build_profile import load_build_profile
from experiment_storage import get_experiment_dir, load_report
from profile_experiment_storage import (
    load_profile_report,
    report_path,
    save_profile_report,
)
from profile_executor_v19 import engine_identity
from profile_scheduler_v18 import (
    candidate_row,
    historical_state,
    metric_point,
    rank_candidate,
    select_diverse,
)

ENGINE_ID = "bababan-test-20261103"
POOL_FILE = "multi_swap_candidate_pool_fullstats_v16.json"
FRONTIER_FILE = "merged_frontier_v23.json"
BATCH_PREFIX = "profile_batch_cycle_"


def make_profile(strict):
    profile = load_build_profile(
        "build_profiles/bababan_test.json"
    )
    if strict:
        profile = deepcopy(profile)
        profile["build"]["name"] += " - Strict Recharge"
        profile["constraints"][
            "max_es_recharge_loss_percent"
        ] = 0.0
    return profile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict-recharge", action="store_true")
    parser.add_argument("--size", type=int, default=10)
    parser.add_argument("--batch-id", required=True)
    args = parser.parse_args()

    if args.size < 1:
        parser.error("--size must be positive")

    import re
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", args.batch_id):
        parser.error("Invalid --batch-id")

    profile = make_profile(args.strict_recharge)
    xml = profile["build"]["xmlPath"]
    group = profile["build"]["skillGroup"]
    directory = get_experiment_dir(xml, group)

    batch_name = BATCH_PREFIX + args.batch_id + ".json"
    output = report_path(profile, batch_name)

    if output.exists():
        raise RuntimeError(
            f"Batch already exists: {output}"
        )

    # Do not create another batch while a previous cycle
    # has unfinished execution or has not been merged.
    for old_path in output.parent.glob(
        BATCH_PREFIX + "*.json"
    ):
        old_name = old_path.name
        old_id = old_name[
            len(BATCH_PREFIX):-len(".json")
        ]
        result_name = (
            "profile_executed_cycle_" + old_id + ".json"
        )
        result_path = report_path(profile, result_name)

        if not result_path.exists():
            raise RuntimeError(
                f"Previous batch not executed: {old_name}"
            )

        old_batch = load_profile_report(
            profile, old_name
        )
        old_result = load_profile_report(
            profile, result_name
        )

        planned = {c["key"] for c in old_batch["candidates"]}
        finished_rows = (
            old_result.get("results", [])
            + old_result.get("invalidTrees", [])
            + old_result.get("invalidCandidates", [])
        )
        finished = [r["key"] for r in finished_rows]

        if len(finished) != len(set(finished)):
            raise RuntimeError(
                f"Duplicate previous results: {result_name}"
            )

        if set(finished) != planned:
            raise RuntimeError(
                f"Unfinished previous batch: {old_name}"
            )

        # A completed batch must be incorporated into an
        # updated frontier before creating another one.
        raise RuntimeError(
            "Previous cycle exists. Refresh the frontier "
            "before scheduling another cycle."
        )

    pool = load_report(directory / POOL_FILE, xml, group)
    if pool.get("version") != "1.2-pool":
        raise RuntimeError("Unexpected pool version")

    historical = load_profile_report(profile, FRONTIER_FILE)
    if historical.get("version") != "2.3":
        raise RuntimeError("Unexpected frontier version")

    # Validate all inputs recorded in Frontier v2.3.
    import hashlib

    def file_sha(path):
        return hashlib.sha256(
            Path(path).read_bytes()
        ).hexdigest()

    engine, fingerprint = engine_identity(ENGINE_ID)

    if historical["engineFingerprint"] != fingerprint:
        raise RuntimeError("Frontier engine mismatch")

    if historical.get("version") != "2.3":
        raise RuntimeError("Unexpected frontier version")

    source_hashes = historical["sourceHashes"]

    cache_name = (
        f"pob_measurements_v19_{fingerprint[:16]}.json"
    )

    if cache_name not in source_hashes:
        raise RuntimeError("Cache missing from frontier sources")

    other_profile = make_profile(
        not args.strict_recharge
    )

    for name, expected_hash in source_hashes.items():
        if name == cache_name:
            source_path = directory / name
        elif name.startswith("otherProfile/"):
            relative_name = name[len("otherProfile/"):]
            source_path = report_path(
                other_profile, relative_name
            )
        else:
            source_path = report_path(profile, name)

        if not source_path.is_file():
            raise RuntimeError(
                f"Missing frontier source: {source_path}"
            )

        if file_sha(source_path) != expected_hash:
            raise RuntimeError(
                f"Stale frontier source: {name}"
            )

    cache = load_report(
        directory / cache_name, xml, group
    )

    if cache.get("version") != "1.9":
        raise RuntimeError("Unexpected cache version")

    if cache.get("engineFingerprint") != fingerprint:
        raise RuntimeError("Cache engine mismatch")

    if cache.get("engine") != engine:
        raise RuntimeError("Cache metadata mismatch")

    cache_keys = set(cache["measurements"])

    legacy_done, conflicts = historical_state(
        directory, xml, group
    )

    overlap = legacy_done & cache_keys
    if overlap:
        raise RuntimeError(
            f"Legacy/cache overlap: {list(overlap)[:5]}"
        )

    done = legacy_done | cache_keys

    # Never schedule a candidate that's already calculated.
    frontier_points = [
        metric_point(row["changes"])
        for row in historical["frontier"]
    ]

    baseline = load_report(
        directory / "swap_executed.json", xml, group
    )["baseline"]

    passing = []
    rejected = []
    counts = Counter()

    for candidate in pool["candidates"]:
        key = candidate["key"]

        if key in done:
            counts["completed"] += 1
            continue

        removal = tuple(sorted(candidate["removeIds"]))
        if removal in conflicts:
            counts["topology_filtered"] += 1
            continue

        checked = evaluate_constraints(
            baseline,
            candidate_row(candidate),
            limits=profile["constraints"],
        )

        score, pareto_candidate = rank_candidate(
            candidate,
            checked,
            frontier_points,
        )

        result = dict(candidate)
        result["legacyPredictedStatus"] = candidate[
            "predictedStatus"
        ]
        result["predictedStatus"] = checked["status"]
        result["predictedProblems"] = checked["problems"]
        result["predictedDpsPercent"] = round(
            checked["changes"]["dps_percent"], 6
        )
        result["predictedEhpPercent"] = round(
            checked["changes"]["ehp_percent"], 6
        )
        result["predictedManaRegenPercent"] = round(
            checked["changes"]["mana_regen_percent"], 6
        )
        result["profileRankingScore"] = round(score, 6)
        result["paretoCandidate"] = pareto_candidate

        counts[checked["status"]] += 1

        if checked["status"] == "PASS":
            passing.append(result)
        elif (
            len(checked["problems"]) <= 2
            and checked["changes"]["dps_percent"] >= 0
        ):
            rejected.append(result)

    for group_rows in (passing, rejected):
        group_rows.sort(
            key=lambda x: (
                -x["profileRankingScore"], x["key"]
            )
        )

    reject_target = (
        max(1, args.size // 5)
        if args.size >= 5 else 0
    )
    pass_target = args.size - reject_target

    used_removals = set()
    selected = select_diverse(
        passing, pass_target, used_removals
    )
    selected += select_diverse(
        rejected, reject_target, used_removals
    )

    if len(selected) < args.size:
        selected_keys = {x["key"] for x in selected}
        remaining = [
            x for x in passing + rejected
            if x["key"] not in selected_keys
        ]
        selected += remaining[
            :args.size - len(selected)
        ]

    keys = [row["key"] for row in selected]

    if len(keys) != len(set(keys)):
        raise RuntimeError("Duplicate selected keys")

    if set(keys) & done:
        raise RuntimeError("Already calculated key selected")

    if any(
        tuple(sorted(row["removeIds"])) in conflicts
        for row in selected
    ):
        raise RuntimeError("Known topology conflict selected")

    import hashlib

    def file_sha(path):
        return hashlib.sha256(
            Path(path).read_bytes()
        ).hexdigest()

    report = {
        "version": "2.4",
        "batchId": args.batch_id,
        "frontierSha256": file_sha(
            report_path(profile, FRONTIER_FILE)
        ),
        "poolSha256": file_sha(
            directory / POOL_FILE
        ),
        "engineFingerprint": fingerprint,
        "poolFile": POOL_FILE,
        "frontierFile": FRONTIER_FILE,
        "historicalAttempts": len(legacy_done),
        "cachedMeasurements": len(cache_keys),
        "completedUniqueAttempts": len(done),
        "knownRemovalConflicts": len(conflicts),
        "availablePredictedPass": counts["PASS"],
        "availablePredictedReject": counts["REJECT"],
        "planned": len(selected),
        "candidates": selected,
    }

    saved = save_profile_report(
        profile, batch_name, report
    )

    print("=== PROFILE SCHEDULER v2.4 ===")
    print("Profile:", profile["build"]["name"])
    print("Pool:", len(pool["candidates"]))
    print("Legacy attempts:", len(legacy_done))
    print("Shared measurements:", len(cache_keys))
    print("Completed unique attempts:", len(done))
    print("Removal conflicts:", len(conflicts))
    print("Available PASS:", counts["PASS"])
    print("Available REJECT:", counts["REJECT"])
    print("Selected:", len(selected))
    print("Already calculated keys selected: 0")

    print("\nSELECTED:")
    for row in selected:
        print(
            row["key"],
            row["predictedStatus"],
            "DPS:", row["predictedDpsPercent"],
            "Score:", row["profileRankingScore"],
        )

    print("\nSaved:", saved)
    print("PoB calls: 0")
    print("Legacy reports: UNCHANGED")


if __name__ == "__main__":
    main()
