
# PoE BuildLab AI — Adaptive Multi-Swap Loop v1.2

import argparse
import os
import subprocess
import sys
from pathlib import Path

from experiment_storage import get_experiment_dir, load_report

ROOT = Path(__file__).resolve().parent
BATCH = "multi_swap_batch_v12.json"
RESULTS = "multi_swap_executed_v12.json"


def run(script, *args):
    print(f"\n>>> {script} {' '.join(map(str, args))}",
          flush=True)
    subprocess.run(
        [sys.executable, str(ROOT / script),
         *map(str, args)],
        cwd=ROOT,
        check=True,
    )


def completed(report):
    return (
        report.get("results", [])
        + report.get("invalidTrees", [])
        + report.get("invalidCandidates", [])
    )


def progress(directory, xml):
    path = directory / RESULTS
    if not path.exists():
        return set()
    report = load_report(path, xml, 6)
    keys = [x["key"] for x in completed(report)]
    if len(keys) != len(set(keys)):
        raise RuntimeError("Duplicate execution keys")
    return set(keys)


def unfinished_batch(directory, xml, done):
    path = directory / BATCH
    if not path.exists():
        return 0

    batch = load_report(path, xml, 6)
    keys = [c["key"] for c in batch["candidates"]]

    if len(keys) != len(set(keys)):
        raise RuntimeError("Duplicate batch keys")

    return sum(key not in done for key in keys)


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

    xml = Path(raw).resolve()
    if not xml.is_file():
        raise RuntimeError("Build XML not found")

    directory = get_experiment_dir(xml, 6)
    start = progress(directory, xml)

    print("=== ADAPTIVE MULTI-SWAP LOOP v1.2 ===")
    print("Existing v1.2 attempts:", len(start))
    print("New attempt budget:", args.budget)
    print("Batch size:", args.batch_size)

    while True:
        before = progress(directory, xml)
        used = len(before - start)
        budget_left = args.budget - used

        if budget_left <= 0:
            break

        pending_batch = unfinished_batch(
            directory, xml, before
        )

        if pending_batch == 0:
            run("pareto_engine.py")
            run(
                "multi_swap_scheduler.py",
                "--size",
                min(args.batch_size, budget_left),
            )
            pending_batch = unfinished_batch(
                directory, xml, before
            )

        if pending_batch == 0:
            print("Candidate pool exhausted.")
            break

        limit = min(
            args.batch_size,
            budget_left,
            pending_batch,
        )

        run(
            "multi_swap_executor.py",
            "--limit", limit,
        )

        after = progress(directory, xml)
        advanced = len(after - before)

        if not before.issubset(after):
            raise RuntimeError("Previous results disappeared")

        if advanced != limit:
            raise RuntimeError(
                f"Expected {limit} new attempts, got {advanced}"
            )

        print(
            f"\nBATCH COMPLETE: {advanced} attempts, "
            f"{len(after - start)}/{args.budget} budget used",
            flush=True,
        )

    run("pareto_engine.py")

    final = progress(directory, xml)
    frontier = load_report(
        directory / "pareto_frontier.json",
        xml, 6,
    )

    print("\n=== ADAPTIVE MULTI-SWAP v1.2 COMPLETE ===")
    print("New attempts:", len(final - start))
    print("Total v1.2 attempts:", len(final))
    print("Total PASS:", frontier["totalPass"])
    print(
        "Pareto combinations:",
        frontier["frontierCombinations"],
    )
    print(
        "Unique Pareto points:",
        frontier["uniqueMetricPoints"],
    )


if __name__ == "__main__":
    main()
