
# PoE BuildLab AI — Profile Re-Evaluator v1.3
# Re-evaluates saved PoB stats without launching PoB.
# Never modifies legacy experiment reports.

import argparse
import hashlib
from copy import deepcopy
from pathlib import Path

from build_constraints import evaluate_constraints
from build_profile import load_build_profile
from experiment_storage import (
    get_experiment_dir,
    load_report,
)
from profile_experiment_storage import (
    load_profile_report,
    report_path,
    save_profile_report,
)

SOURCE_FILE = "multi_swap_executed_v12.json"
BASELINE_FILE = "swap_executed.json"
OUTPUT_FILE = "evaluated_results.json"


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reconstruct_row(saved):
    # Reconstruct the original evaluated row from a
    # double-swap report without changing its PoB stats.

    key = saved["key"]

    if key.count("->") != 1:
        raise ValueError(f"Invalid swap key: {key}")

    remove_part, add_part = key.split("->")

    removes = remove_part.split(",")
    adds = add_part.split(",")

    if len(removes) != 2 or len(adds) != 2:
        raise ValueError(f"Expected double swap: {key}")

    if not all(x.isdigit() for x in removes + adds):
        raise ValueError(f"Invalid node IDs: {key}")

    if not isinstance(saved.get("stats"), dict):
        raise ValueError(f"Missing saved stats: {key}")

    if "ATTRIBUTE_OR_PASSIVE_VALIDATION" in saved.get(
        "problems", []
    ):
        raise ValueError(
            f"Cannot reconstruct validation: {key}"
        )

    return {
        "removeId": saved.get("removeId", remove_part),
        "addId": saved.get("addId", add_part),
        "removeName": saved.get("removeName", ""),
        "addName": saved.get("addName", ""),
        "stats": saved["stats"],
        "validation": {"status": "VALID"},
    }


def evaluate_profile(profile, source, baseline):
    results = []

    for saved in source["results"]:
        row = reconstruct_row(saved)

        checked = evaluate_constraints(
            baseline,
            row,
            limits=profile["constraints"],
        )

        checked["key"] = saved["key"]
        results.append(checked)

    return results


def verify_legacy(source, evaluated):
    if len(source["results"]) != len(evaluated):
        raise RuntimeError("Result count mismatch")

    for original, new in zip(source["results"], evaluated):
        for field in ("key", "status", "problems", "changes"):
            if original.get(field) != new.get(field):
                raise RuntimeError(
                    f"Legacy mismatch in {field}: "
                    f"{original.get('key')}"
                )

    return True


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

    source_path = directory / SOURCE_FILE
    baseline_path = directory / BASELINE_FILE

    source_hash = file_hash(source_path)
    baseline_hash = file_hash(baseline_path)

    source = load_report(
        source_path, xml, skill_group
    )
    baseline_report = load_report(
        baseline_path, xml, skill_group
    )

    if source.get("version") != "1.2":
        raise RuntimeError("Unsupported source report version")

    if source.get("errors"):
        raise RuntimeError("Source report contains errors")

    baseline = baseline_report["baseline"]

    results = evaluate_profile(
        profile, source, baseline
    )

    original_pass = sum(
        row["status"] == "PASS"
        for row in source["results"]
    )
    evaluated_pass = sum(
        row["status"] == "PASS"
        for row in results
    )

    if not args.strict_recharge:
        verify_legacy(source, results)

    status_changes = [
        (old["key"], old["status"], new["status"])
        for old, new in zip(source["results"], results)
        if old["status"] != new["status"]
    ]

    report = {
        "version": "1.3",
        "sourceReport": SOURCE_FILE,
        "sourceReportSha256": source_hash,
        "baselineReport": BASELINE_FILE,
        "baselineReportSha256": baseline_hash,
        "constraints": profile["constraints"],
        "calculated": len(results),
        "passed": evaluated_pass,
        "rejected": len(results) - evaluated_pass,
        "statusChanges": [
            {
                "key": key,
                "before": before,
                "after": after,
            }
            for key, before, after in status_changes
        ],
        "results": results,
    }

    destination = report_path(profile, OUTPUT_FILE)

    if destination.exists():
        previous = load_profile_report(
            profile, OUTPUT_FILE
        )

        for field, expected in (
            ("sourceReportSha256", source_hash),
            ("baselineReportSha256", baseline_hash),
        ):
            if previous.get(field) != expected:
                raise RuntimeError(
                    f"Existing report has different {field}. "
                    "Refusing overwrite."
                )

    saved_path = save_profile_report(
        profile,
        OUTPUT_FILE,
        report,
    )

    print("=== PROFILE RE-EVALUATOR v1.3 ===")
    print("Profile:", profile["build"]["name"])
    print("Calculated PoB results reused:", len(results))
    print("Original PASS:", original_pass)
    print("Profile PASS:", evaluated_pass)
    print("Profile REJECT:", len(results) - evaluated_pass)
    print("Changed statuses:", len(status_changes))

    for key, before, after in status_changes[:15]:
        print(f"  {key}: {before} -> {after}")

    print("Saved:", saved_path)
    print("PoB calls: 0")


if __name__ == "__main__":
    main()
