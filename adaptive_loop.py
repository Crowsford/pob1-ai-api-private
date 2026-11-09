
# PoE BuildLab AI — Adaptive Loop v0.7
# Rebuild queue, run PoB screening, repeat.
# Uses the existing Screening Engine and Adaptive Queue.

import argparse
import os
import subprocess
import sys
from pathlib import Path

from experiment_storage import (
    get_experiment_dir,
    load_report,
    xml_sha256,
)

SKILL_GROUP = 6
ROOT = Path(__file__).resolve().parent


def run_script(filename, *arguments):
    command = [
        sys.executable,
        str(ROOT / filename),
        *map(str, arguments),
    ]

    subprocess.run(
        command,
        cwd=ROOT,
        check=True,
    )


def read_progress(directory, xml_path):
    report = load_report(
        directory / "screening_engine.json",
        xml_path,
        SKILL_GROUP,
    )

    results = report.get("results", [])
    invalid_trees = report.get("invalidTrees", [])
    invalid_candidates = report.get("invalidCandidates", [])

    processed = (
        len(results)
        + len(invalid_trees)
        + len(invalid_candidates)
    )

    keys = (
        [x["key"] for x in results]
        + [x["key"] for x in invalid_trees]
        + [x["key"] for x in invalid_candidates]
    )

    if len(keys) != len(set(keys)):
        raise RuntimeError(
            "Duplicate experiments in screening report"
        )

    return processed, report.get("complete", False)


def main():
    parser = argparse.ArgumentParser(
        description="Automatic PoE screening loop"
    )

    parser.add_argument(
        "--budget",
        type=int,
        default=100,
        help="Maximum NEW experiments in this invocation",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Rebuild predictions after every N experiments",
    )

    args = parser.parse_args()

    if args.budget < 1:
        parser.error("--budget must be positive")

    if args.batch_size < 1:
        parser.error("--batch-size must be positive")

    xml_raw = os.environ.get("BUILD_XML")

    if not xml_raw:
        raise RuntimeError("BUILD_XML is not set")

    xml_path = Path(xml_raw).resolve()
    original_hash = xml_sha256(xml_path)

    directory = get_experiment_dir(
        xml_path,
        SKILL_GROUP,
    )

    initial_count, complete = read_progress(
        directory, xml_path
    )

    print("=== ADAPTIVE LOOP v0.7 ===")
    print("Build:", xml_path.name)
    print("Budget:", args.budget)
    print("Batch size:", args.batch_size)
    print("Already processed by engine:", initial_count)
    print(flush=True)

    if complete:
        print("All planned experiments already complete.")
        return

    batch_number = 0

    while True:
        if xml_sha256(xml_path) != original_hash:
            raise RuntimeError(
                "Build XML changed during adaptive loop"
            )

        current_count, complete = read_progress(
            directory, xml_path
        )

        consumed = current_count - initial_count
        remaining_budget = args.budget - consumed

        if consumed < 0:
            raise RuntimeError(
                "Screening progress moved backwards"
            )

        if complete or remaining_budget <= 0:
            break

        current_limit = min(
            args.batch_size,
            remaining_budget,
        )

        batch_number += 1

        print(
            f"\n=== BATCH {batch_number} ===",
            flush=True,
        )
        print(
            f"Budget remaining: {remaining_budget}",
            flush=True,
        )

        # Rebuild predictions using all latest results.
        run_script("adaptive_queue.py")

        # Run a bounded batch of new PoB experiments.
        run_script(
            "screening_engine.py",
            "--queue",
            "--limit",
            current_limit,
        )

        new_count, complete = read_progress(
            directory, xml_path
        )

        progress = new_count - current_count

        if progress < 0:
            raise RuntimeError(
                "Screening result count decreased"
            )

        if progress > current_limit:
            raise RuntimeError(
                "Screening exceeded its experiment budget"
            )

        if progress == 0 and not complete:
            raise RuntimeError(
                "No progress. Stopping to prevent an "
                "infinite loop."
            )

        if xml_sha256(xml_path) != original_hash:
            raise RuntimeError(
                "Build XML changed during experiment"
            )

        print(
            f"Batch finished: {progress} attempts",
            flush=True,
        )

    final_count, complete = read_progress(
        directory, xml_path
    )

    consumed = final_count - initial_count

    print("\n=== ADAPTIVE LOOP SUMMARY ===")
    print("Experiments this run:", consumed)
    print("Engine completed total:", final_count)
    print("Budget remaining:", args.budget - consumed)
    print("All combinations complete:", complete)
    print("Result directory:", directory)


if __name__ == "__main__":
    main()
