
# PoE BuildLab AI — Profile Frontier Merger v2.5
# Historical experiments + cumulative shared PoB cache.
# Read-only sources. Versioned profile output. No PoB calls.

import argparse
import hashlib
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
from profile_identity import profile_fingerprint
from profile_pareto import build_frontier

ENGINE_ID = "bababan-test-20261103"
HISTORY = "historical_evaluated_results.json"
OUTPUT = "merged_frontier_v25.json"

GENERATIONS = (
    ("profile_batch_v18.json", "profile_executed_v19.json"),
    ("profile_batch_v21.json", "profile_executed_v22.json"),
    ("profile_batch_cycle_0001.json",
     "profile_executed_cycle_0001.json"),
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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


def completed(report):
    return (
        report.get("results", [])
        + report.get("invalidTrees", [])
        + report.get("invalidCandidates", [])
    )


def as_row(measurement):
    removes, adds = measurement["key"].split("->", 1)
    return {
        "removeId": removes,
        "addId": adds,
        "removeName": "",
        "addName": "",
        "stats": measurement["stats"],
        "validation": measurement["validation"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict-recharge", action="store_true")
    args = parser.parse_args()

    profile = make_profile(args.strict_recharge)
    xml = profile["build"]["xmlPath"]
    group = profile["build"]["skillGroup"]
    directory = get_experiment_dir(xml, group)

    destination = report_path(profile, OUTPUT)
    if destination.exists():
        raise RuntimeError(
            "v2.3 snapshot already exists; refusing overwrite"
        )

    history = load_profile_report(profile, HISTORY)

    if history["calculated"] != len(history["results"]):
        raise RuntimeError("Historical count mismatch")

    for filename, expected in history["sourceHashes"].items():
        if sha(directory / filename) != expected:
            raise RuntimeError(
                f"Historical source changed: {filename}"
            )

    baseline_path = directory / "swap_executed.json"
    baseline = load_report(
        baseline_path, xml, group
    )["baseline"]

    engine, fingerprint = engine_identity(ENGINE_ID)

    cache_name = (
        f"pob_measurements_v19_{fingerprint[:16]}.json"
    )
    cache_path = directory / cache_name
    cache = load_report(cache_path, xml, group)

    if (
        cache.get("engineFingerprint") != fingerprint
        or cache.get("engine") != engine
        or cache.get("version") != "1.9"
    ):
        raise RuntimeError("Shared cache identity mismatch")

    measurements = cache["measurements"]

    if not isinstance(measurements, dict):
        raise RuntimeError("Invalid measurements dictionary")

    # Verify all profile execution reports, including
    # calculated and invalid outcomes.
    observed = {}
    source_hashes = {
        HISTORY: sha(report_path(profile, HISTORY)),
        cache_name: sha(cache_path),
    }

    for batch_name, result_name in GENERATIONS:
        batch_path = report_path(profile, batch_name)
        result_path = report_path(profile, result_name)

        batch = load_profile_report(profile, batch_name)
        executed = load_profile_report(profile, result_name)

        if executed["batchSha256"] != sha(batch_path):
            raise RuntimeError(
                f"Batch fingerprint mismatch: {result_name}"
            )

        if executed["engineFingerprint"] != fingerprint:
            raise RuntimeError(
                f"Engine mismatch: {result_name}"
            )

        batch_keys = [
            item["key"] for item in batch["candidates"]
        ]

        if len(batch_keys) != len(set(batch_keys)):
            raise RuntimeError("Duplicate batch keys")

        if len(batch_keys) != batch["planned"]:
            raise RuntimeError("Batch size mismatch")

        rows = completed(executed)
        keys = [item["key"] for item in rows]

        if len(keys) != len(set(keys)):
            raise RuntimeError("Duplicate execution results")

        if set(keys) != set(batch_keys):
            raise RuntimeError(
                f"Incomplete execution: {result_name}"
            )

        for saved in rows:
            key = saved["key"]

            if key in observed:
                raise RuntimeError(
                    f"Repeated profile result: {key}"
                )

            measured = measurements.get(key)
            if measured is None or measured["key"] != key:
                raise RuntimeError(
                    f"Measurement missing or mismatched: {key}"
                )

            kind = measured["kind"]

            if kind == "CALCULATED":
                if saved not in executed["results"]:
                    raise RuntimeError(
                        f"Calculated result in wrong section: {key}"
                    )

                checked = evaluate_constraints(
                    baseline,
                    as_row(measured),
                    limits=profile["constraints"],
                )

                for field in ("status", "problems", "changes"):
                    if checked[field] != saved[field]:
                        raise RuntimeError(
                            f"Evaluation mismatch: {key} {field}"
                        )

                if (
                    measured["stats"] != saved["stats"]
                    or measured["validation"]
                    != saved["validation"]
                    or saved.get("profileFingerprint")
                    != profile_fingerprint(profile)
                ):
                    raise RuntimeError(
                        f"Measurement mismatch: {key}"
                    )

            elif kind == "INVALID_TREE":
                if saved not in executed["invalidTrees"]:
                    raise RuntimeError(
                        f"Invalid tree in wrong section: {key}"
                    )
                if saved != measured:
                    raise RuntimeError(
                        f"Invalid tree mismatch: {key}"
                    )

            elif kind == "INVALID_CANDIDATE":
                if saved not in executed["invalidCandidates"]:
                    raise RuntimeError(
                        f"Invalid candidate in wrong section: {key}"
                    )
                if saved != measured:
                    raise RuntimeError(
                        f"Invalid candidate mismatch: {key}"
                    )
            else:
                raise RuntimeError(
                    f"Unknown measurement kind: {key}"
                )

            observed[key] = kind

        source_hashes[batch_name] = sha(batch_path)
        source_hashes[result_name] = sha(result_path)

    # Each profile may have scheduled different candidates.
    # Every cache entry must be backed by at least one
    # completed execution report across the two profiles.
    extra = set(observed) - set(measurements)
    if extra:
        raise RuntimeError(
            f"Profile results absent from cache: {sorted(extra)[:5]}"
        )

    missing = set(measurements) - set(observed)

    other_profile = make_profile(not args.strict_recharge)
    confirmed_elsewhere = set()

    for batch_name, result_name in GENERATIONS:
        other_batch_path = report_path(other_profile, batch_name)
        other_result_path = report_path(other_profile, result_name)

        other_batch = load_profile_report(
            other_profile, batch_name
        )
        other_executed = load_profile_report(
            other_profile, result_name
        )

        if other_executed.get("batchSha256") != sha(
            other_batch_path
        ):
            raise RuntimeError(
                f"Other profile batch mismatch: {result_name}"
            )

        if other_executed.get("engineFingerprint") != fingerprint:
            raise RuntimeError(
                f"Other profile engine mismatch: {result_name}"
            )

        batch_keys = [
            item["key"] for item in other_batch["candidates"]
        ]
        rows = completed(other_executed)
        result_keys = [item["key"] for item in rows]

        if (
            len(batch_keys) != len(set(batch_keys))
            or len(result_keys) != len(set(result_keys))
            or set(batch_keys) != set(result_keys)
        ):
            raise RuntimeError(
                f"Other profile batch incomplete: {result_name}"
            )

        for saved in rows:
            key = saved["key"]

            if key not in missing:
                continue

            if key in confirmed_elsewhere:
                raise RuntimeError(
                    f"Duplicate external confirmation: {key}"
                )

            measured = measurements[key]
            kind = measured["kind"]

            if kind == "CALCULATED":
                if saved not in other_executed["results"]:
                    raise RuntimeError(
                        f"Wrong external result section: {key}"
                    )

                if (
                    saved["stats"] != measured["stats"]
                    or saved["validation"] != measured["validation"]
                ):
                    raise RuntimeError(
                        f"External measurement mismatch: {key}"
                    )

                checked = evaluate_constraints(
                    baseline,
                    as_row(measured),
                    limits=other_profile["constraints"],
                )

                for field in ("status", "problems", "changes"):
                    if checked[field] != saved[field]:
                        raise RuntimeError(
                            f"External evaluation mismatch: {key} {field}"
                        )

                if saved.get("profileFingerprint") != profile_fingerprint(
                    other_profile
                ):
                    raise RuntimeError(
                        f"External profile identity mismatch: {key}"
                    )

            elif kind == "INVALID_TREE":
                if (
                    saved not in other_executed["invalidTrees"]
                    or saved != measured
                ):
                    raise RuntimeError(
                        f"External invalid tree mismatch: {key}"
                    )

            elif kind == "INVALID_CANDIDATE":
                if (
                    saved not in other_executed["invalidCandidates"]
                    or saved != measured
                ):
                    raise RuntimeError(
                        f"External invalid candidate mismatch: {key}"
                    )

            else:
                raise RuntimeError(
                    f"Unknown external measurement kind: {key}"
                )

            confirmed_elsewhere.add(key)

        source_hashes[
            "otherProfile/" + batch_name
        ] = sha(other_batch_path)
        source_hashes[
            "otherProfile/" + result_name
        ] = sha(other_result_path)

    unconfirmed = missing - confirmed_elsewhere

    if unconfirmed:
        raise RuntimeError(
            "Unconfirmed shared measurements: "
            f"{sorted(unconfirmed)[:10]}"
        )

    print("Locally confirmed:", len(observed))
    print("Confirmed via other profile:", len(confirmed_elsewhere))
    print("Unconfirmed measurements:", len(unconfirmed))

    merged = list(history["results"])
    historical_keys = [row["key"] for row in merged]

    if len(historical_keys) != len(set(historical_keys)):
        raise RuntimeError("Duplicate historical keys")

    if set(historical_keys) & set(measurements):
        raise RuntimeError("Historical/cache key overlap")

    new_counts = Counter()

    for key, measurement in sorted(measurements.items()):
        kind = measurement["kind"]
        new_counts[kind] += 1

        if kind != "CALCULATED":
            continue

        checked = evaluate_constraints(
            baseline,
            as_row(measurement),
            limits=profile["constraints"],
        )
        checked["key"] = key
        checked["sourceReport"] = cache_name
        checked["validationProvenance"] = "recorded"

        merged.append(checked)
        new_counts[checked["status"]] += 1

    frontier, unique_points = build_frontier(merged)

    total_pass = sum(
        row["status"] == "PASS" for row in merged
    )
    total_reject = len(merged) - total_pass

    report = {
        "version": "2.5",
        "engineFingerprint": fingerprint,
        "sourceHashes": source_hashes,
        "historicalCalculated": len(history["results"]),
        "newMeasurements": len(measurements),
        "newCalculated": new_counts["CALCULATED"],
        "newInvalidTrees": new_counts["INVALID_TREE"],
        "newInvalidCandidates": new_counts["INVALID_CANDIDATE"],
        "newPass": new_counts["PASS"],
        "newReject": new_counts["REJECT"],
        "completedUniqueAttempts": (
            len(historical_keys) + len(measurements)
        ),
        "totalCalculated": len(merged),
        "totalPass": total_pass,
        "totalReject": total_reject,
        "metrics": [
            "dps_percent",
            "ehp_percent",
            "mana_regen_percent",
        ],
        "frontierCount": len(frontier),
        "uniqueMetricPoints": unique_points,
        "frontier": frontier,
    }

    saved = save_profile_report(profile, OUTPUT, report)

    print("=== PROFILE FRONTIER MERGER v2.5 ===")
    print("Profile:", profile["build"]["name"])
    print("Historical calculated:", len(history["results"]))
    print("Shared cache entries:", len(measurements))
    print("New calculated:", new_counts["CALCULATED"])
    print("New invalid trees:", new_counts["INVALID_TREE"])
    print(
        "New invalid candidates:",
        new_counts["INVALID_CANDIDATE"],
    )
    print("New PASS:", new_counts["PASS"])
    print("New REJECT:", new_counts["REJECT"])
    print("Total calculated:", len(merged))
    print("Total PASS:", total_pass)
    print("Total REJECT:", total_reject)
    print("Pareto combinations:", len(frontier))
    print("Unique metric points:", unique_points)
    print("Saved:", saved)
    print("PoB calls: 0")


if __name__ == "__main__":
    main()
