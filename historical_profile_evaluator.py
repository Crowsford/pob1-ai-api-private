
# PoE BuildLab AI — Historical Profile Evaluator v1.5
# Read-only legacy sources. No PoB calls.

import argparse
import hashlib
from collections import Counter
from copy import deepcopy

from build_constraints import evaluate_constraints
from build_profile import load_build_profile
from experiment_storage import get_experiment_dir, load_report
from pareto_engine import REPORTS
from profile_experiment_storage import (
    report_path,
    save_profile_report,
)
from profile_pareto import build_frontier

SOURCE_FILES = REPORTS + ("multi_swap_executed_v12.json",)
BASELINE_FILE = "swap_executed.json"

EVALUATION_FILE = "historical_evaluated_results.json"
FRONTIER_FILE = "historical_pareto_frontier.json"


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reconstruct_row(saved):
    key = saved["key"]
    parts = key.split("->")

    if len(parts) != 2:
        raise ValueError(f"Invalid key: {key}")

    removes, adds = parts

    if (
        len(removes.split(",")) != 2
        or len(adds.split(",")) != 2
        or not all(
            x.isdigit()
            for x in removes.split(",") + adds.split(",")
        )
    ):
        raise ValueError(f"Invalid double swap: {key}")

    if not isinstance(saved["stats"], dict):
        raise ValueError(f"Missing stats: {key}")

    validation = saved.get("validation")

    if validation is None:
        if "ATTRIBUTE_OR_PASSIVE_VALIDATION" in saved["problems"]:
            raise ValueError(
                f"Cannot reconstruct validation: {key}"
            )

        validation = {"status": "VALID"}
        provenance = "inferred_from_legacy_result"
    else:
        if not isinstance(validation, dict):
            raise ValueError(f"Invalid validation: {key}")
        provenance = "recorded"

    return {
        "removeId": saved.get("removeId", removes),
        "addId": saved.get("addId", adds),
        "removeName": saved.get("removeName", ""),
        "addName": saved.get("addName", ""),
        "stats": saved["stats"],
        "validation": validation,
    }, provenance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        default="build_profiles/bababan_test.json",
    )
    parser.add_argument(
        "--strict-recharge",
        action="store_true",
    )
    args = parser.parse_args()

    profile = load_build_profile(args.profile)

    if args.strict_recharge:
        profile = deepcopy(profile)
        profile["build"]["name"] += " - Strict Recharge"
        profile["constraints"][
            "max_es_recharge_loss_percent"
        ] = 0.0

    xml = profile["build"]["xmlPath"]
    skill_group = profile["build"]["skillGroup"]
    directory = get_experiment_dir(xml, skill_group)

    baseline_path = directory / BASELINE_FILE
    baseline_report = load_report(
        baseline_path, xml, skill_group
    )
    baseline = baseline_report["baseline"]

    source_hashes = {
        BASELINE_FILE: sha256_file(baseline_path)
    }

    seen = {}
    results = []
    mismatches = []
    provenance_counts = Counter()
    source_counts = {}
    status_changes = []

    for filename in SOURCE_FILES:
        path = directory / filename
        report = load_report(path, xml, skill_group)

        if report.get("errors"):
            raise RuntimeError(
                f"Source contains errors: {filename}"
            )

        source_hashes[filename] = sha256_file(path)
        rows = report["results"]
        source_counts[filename] = len(rows)

        for saved in rows:
            key = saved["key"]

            if key in seen:
                raise RuntimeError(
                    f"Duplicate key: {key} "
                    f"in {seen[key]} and {filename}"
                )

            seen[key] = filename

            if saved["status"] not in ("PASS", "REJECT"):
                raise RuntimeError(
                    f"Unexpected status: {filename}: {key}"
                )

            row, provenance = reconstruct_row(saved)
            provenance_counts[provenance] += 1

            checked = evaluate_constraints(
                baseline,
                row,
                limits=profile["constraints"],
            )

            # First verify that the new evaluator reproduces
            # the legacy calculations under the ORIGINAL limits.
            original = evaluate_constraints(
                baseline, row
            )

            differences = [
                field
                for field in ("status", "problems", "changes")
                if original[field] != saved.get(field)
            ]

            if differences:
                mismatches.append({
                    "key": key,
                    "source": filename,
                    "fields": differences,
                    "savedStatus": saved["status"],
                    "recomputedStatus": original["status"],
                })

            if saved["status"] != checked["status"]:
                status_changes.append({
                    "key": key,
                    "source": filename,
                    "before": saved["status"],
                    "after": checked["status"],
                })

            checked["key"] = key
            checked["sourceReport"] = filename
            checked["validationProvenance"] = provenance

            results.append(checked)

    print("=== HISTORICAL PROFILE EVALUATOR v1.5 ===")
    print("Profile:", profile["build"]["name"])
    print("Source files:", len(SOURCE_FILES))
    print("Calculated rows:", len(results))
    print("Unique keys:", len(seen))
    print("Validation provenance:", dict(provenance_counts))
    print("Legacy mismatches:", len(mismatches))

    for item in mismatches[:15]:
        print("  MISMATCH:", item)

    if mismatches:
        raise RuntimeError(
            "Legacy compatibility failed. "
            "No profile reports were written."
        )

    if len(results) != 271:
        raise RuntimeError(
            f"Unexpected history size: {len(results)}"
        )

    if len(seen) != len(results):
        raise RuntimeError("Duplicate results detected")

    passed = sum(r["status"] == "PASS" for r in results)

    frontier, unique_points = build_frontier(results)

    print("PASS:", passed)
    print("REJECT:", len(results) - passed)
    print("Changed statuses:", len(status_changes))
    print("Frontier combinations:", len(frontier))
    print("Unique metric points:", unique_points)

    for item in status_changes[:15]:
        print(
            "  CHANGE:",
            item["key"],
            item["before"],
            "->",
            item["after"],
        )

    evaluation = {
        "version": "1.5",
        "baselineReport": BASELINE_FILE,
        "sourceHashes": source_hashes,
        "sourceCounts": source_counts,
        "constraints": profile["constraints"],
        "calculated": len(results),
        "passed": passed,
        "rejected": len(results) - passed,
        "validationProvenance": dict(provenance_counts),
        "statusChanges": status_changes,
        "results": results,
    }

    # Refuse to overwrite reports created earlier.
    # Subsequent reruns require an explicit versioned migration.
    eval_path = report_path(profile, EVALUATION_FILE)
    frontier_path = report_path(profile, FRONTIER_FILE)

    if eval_path.exists() or frontier_path.exists():
        raise RuntimeError(
            "Historical profile output already exists; "
            "refusing overwrite"
        )

    saved_eval = save_profile_report(
        profile, EVALUATION_FILE, evaluation
    )

    saved_frontier = save_profile_report(
        profile,
        FRONTIER_FILE,
        {
            "version": "1.5",
            "sourceReport": EVALUATION_FILE,
            "sourceReportSha256": sha256_file(saved_eval),
            "metrics": [
                "dps_percent",
                "ehp_percent",
                "mana_regen_percent",
            ],
            "totalCalculated": len(results),
            "totalPass": passed,
            "frontierCount": len(frontier),
            "uniqueMetricPoints": unique_points,
            "frontier": frontier,
        },
    )

    print("\nSaved evaluation:", saved_eval)
    print("Saved frontier:", saved_frontier)
    print("PoB calls: 0")


if __name__ == "__main__":
    main()
