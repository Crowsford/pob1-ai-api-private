
# PoE BuildLab AI — Profile Frontier Merger v2.0
# Historical results + shared PoB measurements.
# No PoB calls. Legacy reports remain untouched.

import argparse
import hashlib
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
from profile_pareto import build_frontier

ENGINE_ID = "bababan-test-20261103"
HISTORY_FILE = "historical_evaluated_results.json"
OUTPUT_FILE = "merged_frontier_v20.json"
BASELINE_FILE = "swap_executed.json"


def sha_file(path):
    return hashlib.sha256(
        Path(path).read_bytes()
    ).hexdigest()


def make_profile(strict=False):
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


def measured_row(measurement):
    key = measurement["key"]
    removes, adds = key.split("->", 1)

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
    parser.add_argument(
        "--strict-recharge",
        action="store_true",
    )
    args = parser.parse_args()

    profile = make_profile(args.strict_recharge)

    xml = profile["build"]["xmlPath"]
    group = profile["build"]["skillGroup"]
    directory = get_experiment_dir(xml, group)

    output_path = report_path(profile, OUTPUT_FILE)

    if output_path.exists():
        raise RuntimeError(
            "Merged report already exists. "
            "Refusing to overwrite an earlier snapshot."
        )

    history_path = report_path(profile, HISTORY_FILE)
    history = load_profile_report(profile, HISTORY_FILE)

    # Verify historical inputs have not changed.
    for filename, expected in history["sourceHashes"].items():
        actual = sha_file(directory / filename)
        if actual != expected:
            raise RuntimeError(
                f"Historical source changed: {filename}"
            )

    baseline_path = directory / BASELINE_FILE
    baseline = load_report(
        baseline_path, xml, group
    )["baseline"]

    engine, fingerprint = engine_identity(ENGINE_ID)

    cache_name = (
        f"pob_measurements_v19_{fingerprint[:16]}.json"
    )
    cache_path = directory / cache_name

    cache = load_report(cache_path, xml, group)

    if cache.get("version") != "1.9":
        raise RuntimeError("Unexpected cache version")

    if cache.get("engineFingerprint") != fingerprint:
        raise RuntimeError("Engine fingerprint mismatch")

    if cache.get("engine") != engine:
        raise RuntimeError("Engine metadata mismatch")

    measurements = cache["measurements"]

    # Verify that the source reports still agree with
    # the shared measurements and the active profile.
    executed_name = "profile_executed_v19.json"
    executed = load_profile_report(
        profile, executed_name
    )

    batch_path = report_path(
        profile, "profile_batch_v18.json"
    )

    if executed.get("batchSha256") != sha_file(batch_path):
        raise RuntimeError("Executed batch hash mismatch")

    if executed.get("engineFingerprint") != fingerprint:
        raise RuntimeError(
            "Executed report engine mismatch"
        )

    for saved in executed["results"]:
        key = saved["key"]
        measured = measurements.get(key)

        if measured is None or measured["kind"] != "CALCULATED":
            raise RuntimeError(
                f"Missing calculated measurement: {key}"
            )

        checked = evaluate_constraints(
            baseline,
            measured_row(measured),
            limits=profile["constraints"],
        )

        for field in ("status", "problems", "changes"):
            if checked[field] != saved[field]:
                raise RuntimeError(
                    f"Profile result mismatch: {key}, {field}"
                )

        if measured["stats"] != saved["stats"]:
            raise RuntimeError(
                f"Stored stats mismatch: {key}"
            )

    historical_rows = history["results"]
    merged = list(historical_rows)

    keys = set()

    for row in historical_rows:
        key = row["key"]
        if key in keys:
            raise RuntimeError(
                f"Duplicate historical key: {key}"
            )
        keys.add(key)

    new_pass = 0
    new_reject = 0

    for key, measured in sorted(measurements.items()):
        if key in keys:
            raise RuntimeError(
                f"Measurement overlaps history: {key}"
            )

        if measured["key"] != key:
            raise RuntimeError(
                f"Cache key mismatch: {key}"
            )

        if measured["kind"] != "CALCULATED":
            raise RuntimeError(
                f"Unsupported measurement kind: {key}"
            )

        row = measured_row(measured)

        checked = evaluate_constraints(
            baseline,
            row,
            limits=profile["constraints"],
        )

        checked["key"] = key
        checked["sourceReport"] = cache_name
        checked["validationProvenance"] = "recorded"

        merged.append(checked)
        keys.add(key)

        if checked["status"] == "PASS":
            new_pass += 1
        else:
            new_reject += 1

    if len(merged) != len(keys):
        raise RuntimeError("Merged key count mismatch")

    expected_total = len(historical_rows) + len(measurements)

    if len(merged) != expected_total:
        raise RuntimeError("Merge count mismatch")

    frontier, unique_count = build_frontier(merged)

    total_pass = sum(
        row["status"] == "PASS"
        for row in merged
    )

    report = {
        "version": "2.0",
        "engineFingerprint": fingerprint,
        "historicalSource": HISTORY_FILE,
        "historicalSourceSha256": sha_file(history_path),
        "measurementSource": cache_name,
        "measurementSourceSha256": sha_file(cache_path),
        "profileExecutorSource": executed_name,
        "profileExecutorSha256": sha_file(
            report_path(profile, executed_name)
        ),
        "metrics": [
            "dps_percent",
            "ehp_percent",
            "mana_regen_percent",
        ],
        "historicalCalculated": len(historical_rows),
        "newMeasurements": len(measurements),
        "totalCalculated": len(merged),
        "totalPass": total_pass,
        "totalReject": len(merged) - total_pass,
        "newPass": new_pass,
        "newReject": new_reject,
        "frontierCount": len(frontier),
        "uniqueMetricPoints": unique_count,
        "frontier": frontier,
    }

    saved_path = save_profile_report(
        profile, OUTPUT_FILE, report
    )

    print("=== PROFILE FRONTIER MERGER v2.0 ===")
    print("Profile:", profile["build"]["name"])
    print("Historical calculations:", len(historical_rows))
    print("New unique measurements:", len(measurements))
    print("Total calculated:", len(merged))
    print("New PASS:", new_pass)
    print("New REJECT:", new_reject)
    print("Total PASS:", total_pass)
    print("Total REJECT:", len(merged) - total_pass)
    print("Frontier combinations:", len(frontier))
    print("Unique metric points:", unique_count)

    print("\nTOP FRONTIER:")
    for row in frontier[:10]:
        changes = row["changes"]
        print(
            row["key"],
            "DPS:", round(changes["dps_percent"], 4),
            "EHP:", round(changes["ehp_percent"], 4),
            "Mana:", round(
                changes["mana_regen_percent"], 4
            ),
        )

    print("\nSaved:", saved_path)
    print("PoB calls: 0")
    print("Legacy reports: UNCHANGED")


if __name__ == "__main__":
    main()
