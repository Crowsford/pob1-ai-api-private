
# PoE BuildLab AI — Adaptive Multi-Swap Loop v1.1
# Rebuild Pareto -> reprioritize -> execute a batch -> repeat.

import argparse
import os
import subprocess
import sys
from pathlib import Path

from experiment_storage import (
    get_experiment_dir,
    load_report,
)


def run_script(filename, *args):
    print(f"\n>>> {filename} {' '.join(map(str, args))}",
          flush=True)

    subprocess.run(
        [sys.executable, filename, *map(str, args)],
        check=True,
    )


def get_progress(xml_path):
    directory = get_experiment_dir(xml_path, 6)

    report = load_report(
        directory / "multi_swap_executed_v11.json",
        xml_path, 6,
    )

    calculated = report.get("results", [])
    invalid_trees = report.get("invalidTrees", [])
    invalid_candidates = report.get("invalidCandidates", [])

    completed = (
        len(calculated)
        + len(invalid_trees)
        + len(invalid_candidates)
    )

    return {
        "completed": completed,
        "pass": sum(
            x["status"] == "PASS" for x in calculated
        ),
        "reject": sum(
            x["status"] == "REJECT" for x in calculated
        ),
        "invalidTrees": len(invalid_trees),
        "invalidCandidates": len(invalid_candidates),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=5)
    args = parser.parse_args()

    if args.budget < 1 or args.batch_size < 1:
        parser.error("Budget and batch size must be positive")

    raw = os.environ.get("BUILD_XML")
    if not raw:
        raise RuntimeError("BUILD_XML is not set")

    xml_path = Path(raw).resolve()

    if not xml_path.is_file():
        raise RuntimeError("Build XML not found")

    before = get_progress(xml_path)
    start_count = before["completed"]

    print("=== ADAPTIVE MULTI-SWAP LOOP v1.1 ===")
    print("Already completed:", start_count)
    print("New attempt budget:", args.budget)
    print("Batch size:", args.batch_size)

    while True:
        current = get_progress(xml_path)
        used = current["completed"] - start_count
        remaining_budget = args.budget - used

        if remaining_budget <= 0:
            break

        # Include all successful results, including the
        # latest v1.1 batch, in the current Pareto frontier.
        run_script("pareto_engine.py")

        # Reorder only untested candidates.
        run_script("multi_swap_queue_v11.py")

        directory = get_experiment_dir(xml_path, 6)
        plan = load_report(
            directory / "multi_swap_plan_v11.json",
            xml_path, 6,
        )

        remaining_plan = (
            len(plan["candidates"]) - current["completed"]
        )

        if remaining_plan <= 0:
            print("Candidate pool exhausted.")
            break

        limit = min(
            args.batch_size,
            remaining_budget,
            remaining_plan,
        )

        run_script(
            "multi_swap_executor_v11.py",
            "--limit", limit,
        )

        after = get_progress(xml_path)
        advanced = after["completed"] - current["completed"]

        if advanced != limit:
            raise RuntimeError(
                f"Expected {limit} new results, got {advanced}"
            )

        print("\n--- BATCH SUMMARY ---")
        print("New attempts so far:",
              after["completed"] - start_count)
        print("Total PASS:", after["pass"])
        print("Total REJECT:", after["reject"])
        print("Invalid trees:", after["invalidTrees"])
        print("Invalid candidates:", after["invalidCandidates"])

    # Refresh the frontier after the final executed batch.
    run_script("pareto_engine.py")

    directory = get_experiment_dir(xml_path, 6)
    frontier = load_report(
        directory / "pareto_frontier.json",
        xml_path, 6,
    )
    final = get_progress(xml_path)

    print("\n=== ADAPTIVE MULTI-SWAP COMPLETE ===")
    print("New attempts:", final["completed"] - start_count)
    print("Total processed in v1.1:", final["completed"])
    print("Total PASS in all reports:", frontier["totalPass"])
    print("Pareto combinations:",
          frontier["frontierCombinations"])
    print("Unique Pareto points:",
          frontier["uniqueMetricPoints"])


if __name__ == "__main__":
    main()
