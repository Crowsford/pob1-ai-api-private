
# PoE BuildLab AI — Persistent Multi-Swap Executor v1.2
# Executes saved batches with resumable, cumulative history.

import argparse
import os
import re
from pathlib import Path

from experiment_runner import evaluate
from experiment_storage import (
    get_experiment_dir,
    load_report,
    save_report,
    xml_sha256,
)
from build_validator import validate_experiment
from build_constraints import evaluate_constraints
from pareto_engine import REPORTS

SKILL_GROUP = 6
BATCH_FILE = "multi_swap_batch_v12.json"
RESULT_FILE = "multi_swap_executed_v12.json"


def completed_rows(report):
    return (
        report.get("results", [])
        + report.get("invalidTrees", [])
        + report.get("invalidCandidates", [])
    )


def historical_keys(directory, xml_path):
    done = set()

    for filename in REPORTS:
        report = load_report(
            directory / filename, xml_path, SKILL_GROUP
        )

        for row in completed_rows(report):
            key = row["key"]
            if key in done:
                raise RuntimeError(
                    f"Duplicate historical key: {key}"
                )
            done.add(key)

    return done


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be positive")

    raw = os.environ.get("BUILD_XML")
    if not raw:
        raise RuntimeError("BUILD_XML is not set")

    xml_path = Path(raw).resolve()
    digest = xml_sha256(xml_path)
    directory = get_experiment_dir(xml_path, SKILL_GROUP)

    batch = load_report(
        directory / BATCH_FILE,
        xml_path, SKILL_GROUP,
    )

    if batch.get("version") != "1.2":
        raise RuntimeError("Unexpected batch version")

    candidates = batch["candidates"]
    batch_keys = [c["key"] for c in candidates]

    if len(batch_keys) != len(set(batch_keys)):
        raise RuntimeError("Duplicate batch keys")

    if len(batch_keys) != batch["planned"]:
        raise RuntimeError("Batch count mismatch")

    prior = historical_keys(directory, xml_path)

    if set(batch_keys) & prior:
        raise RuntimeError(
            "Batch contains an experiment from earlier versions"
        )

    baseline = load_report(
        directory / "swap_executed.json",
        xml_path, SKILL_GROUP,
    )["baseline"]

    output = directory / RESULT_FILE

    if output.exists():
        report = load_report(
            output, xml_path, SKILL_GROUP,
        )
        if report.get("version") != "1.2":
            raise RuntimeError("Unexpected result version")
    else:
        report = {
            "version": "1.2",
            "xmlPath": str(xml_path),
            "xmlSha256": digest,
            "skillGroup": SKILL_GROUP,
            "results": [],
            "invalidTrees": [],
            "invalidCandidates": [],
        }
        save_report(output, report)

    saved = completed_rows(report)
    saved_keys = [row["key"] for row in saved]

    if len(saved_keys) != len(set(saved_keys)):
        raise RuntimeError("Duplicate saved experiment")

    if set(saved_keys) & prior:
        raise RuntimeError(
            "v1.2 results overlap earlier experiments"
        )

    done = set(saved_keys)

    # If the batch was partially executed, resume it.
    pending = [
        c for c in candidates
        if c["key"] not in done
    ]

    print("=== MULTI-SWAP EXECUTOR v1.2 ===")
    print("Historical attempts:", len(prior))
    print("Saved v1.2 attempts:", len(done))
    print("Current batch:", len(candidates))
    print("Pending in batch:", len(pending))
    print("Run limit:", args.limit, flush=True)

    attempted = 0

    for candidate in pending[:args.limit]:
        if xml_sha256(xml_path) != digest:
            raise RuntimeError("Build XML changed")

        key = candidate["key"]
        removes = list(candidate["removeIds"])
        adds = list(candidate["addIds"])

        canonical = (
            ",".join(map(str, sorted(removes)))
            + "->"
            + ",".join(map(str, sorted(adds)))
        )

        if canonical != key:
            raise RuntimeError(f"Noncanonical key: {key}")

        print(
            f"[{attempted + 1}/"
            f"{min(args.limit, len(pending))}] {key}",
            flush=True,
        )

        try:
            result = evaluate(
                xml_path,
                nodes=adds,
                remove_nodes=removes,
                skill_group=SKILL_GROUP,
            )

        except Exception as exc:
            message = str(exc)

            if "TREE_CONFLICT|" in message:
                match = re.search(
                    r"TREE_CONFLICT\|requested=(\d+)"
                    r"\|disconnected=([0-9,]*)",
                    message,
                )
                if not match:
                    raise RuntimeError(
                        f"Unknown tree conflict: {message}"
                    ) from exc

                report["invalidTrees"].append({
                    "key": key,
                    "requested": int(match.group(1)),
                    "disconnected": [
                        int(x)
                        for x in match.group(2).split(",")
                        if x
                    ],
                })
                print("  INVALID_TREE", flush=True)

            elif "Node requires more than one point:" in message:
                report["invalidCandidates"].append({
                    "key": key,
                    "reason": "MULTI_POINT_REQUIRED",
                    "error": message.splitlines()[0],
                })
                print("  INVALID_CANDIDATE", flush=True)

            else:
                raise RuntimeError(
                    f"Unknown PoB failure for {key}: {message}"
                ) from exc

        else:
            removed = sorted(
                int(x["nodeId"])
                for x in result["removalExperiment"]["nodes"]
            )
            added = sorted(
                int(x["nodeId"])
                for x in result["passiveExperiment"]["nodes"]
            )

            if removed != sorted(removes):
                raise RuntimeError(
                    f"Removed node mismatch: {key}"
                )

            if added != sorted(adds):
                raise RuntimeError(
                    f"Added node mismatch: {key}"
                )

            if (
                result["passivePointsUsed"]
                != baseline["passivePointsUsed"]
            ):
                raise RuntimeError(
                    f"Passive point count changed: {key}"
                )

            validation = validate_experiment(
                baseline, result
            )

            row = {
                "removeId": ",".join(map(str, removes)),
                "removeName": "",
                "addId": ",".join(map(str, adds)),
                "addName": "",
                "stats": result["stats"],
                "validation": validation,
            }

            checked = evaluate_constraints(baseline, row)

            if checked["status"] not in ("PASS", "REJECT"):
                raise RuntimeError(
                    f"Unknown constraint status: {key}"
                )

            report["results"].append({
                "key": key,
                "removeIds": removes,
                "addIds": adds,
                "status": checked["status"],
                "problems": checked["problems"],
                "changes": checked["changes"],
                "stats": result["stats"],
                "validation": validation,
                "predictedStatus": candidate["predictedStatus"],
                "predictedDpsPercent": candidate[
                    "predictedDpsPercent"
                ],
                "predictedEhpPercent": candidate[
                    "predictedEhpPercent"
                ],
                "selectionMode": candidate.get(
                    "selectionMode"
                ),
            })

            print(
                " ", checked["status"],
                "DPS:",
                round(checked["changes"]["dps_percent"], 4),
                "EHP:",
                round(checked["changes"]["ehp_percent"], 4),
                checked["problems"],
                flush=True,
            )

        if xml_sha256(xml_path) != digest:
            raise RuntimeError("Build XML changed")

        # Save immediately after every known outcome.
        save_report(output, report)
        done.add(key)
        attempted += 1

    saved = completed_rows(report)

    print("\n=== MULTI-SWAP v1.2 SUMMARY ===")
    print("New attempts:", attempted)
    print("Total v1.2:", len(saved))
    print("PASS:", sum(
        x["status"] == "PASS"
        for x in report["results"]
    ))
    print("REJECT:", sum(
        x["status"] == "REJECT"
        for x in report["results"]
    ))
    print("Invalid trees:", len(report["invalidTrees"]))
    print(
        "Invalid candidates:",
        len(report["invalidCandidates"]),
    )
    print(
        "Remaining in batch:",
        sum(c["key"] not in done for c in candidates),
    )
    print("Saved:", output)


if __name__ == "__main__":
    main()
