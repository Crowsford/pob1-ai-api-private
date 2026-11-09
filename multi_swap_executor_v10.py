
# PoE BuildLab AI — Multi-Swap Executor v0.8

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

SKILL_GROUP = 6


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

    plan = load_report(
        directory / "multi_swap_plan_v10.json",
        xml_path, SKILL_GROUP,
    )

    if plan.get("version") != "1.0":
        raise RuntimeError("Unsupported plan version")

    candidates = plan["candidates"]
    keys = [x["key"] for x in candidates]

    if len(keys) != len(set(keys)):
        raise RuntimeError("Duplicate planned combinations")

    if len(candidates) != plan["planned"]:
        raise RuntimeError("Incomplete plan")

    baseline = load_report(
        directory / "swap_executed.json",
        xml_path, SKILL_GROUP,
    )["baseline"]

    output = directory / "multi_swap_executed_v10.json"

    if output.exists():
        report = load_report(
            output, xml_path, SKILL_GROUP,
        )
        if (
            report.get("version") != "1.0"
            or report.get("plannedKeys") != keys
        ):
            raise RuntimeError("Saved execution plan mismatch")
    else:
        report = {
            "version": "1.0",
            "xmlPath": str(xml_path),
            "xmlSha256": digest,
            "skillGroup": SKILL_GROUP,
            "plannedKeys": keys,
            "results": [],
            "invalidTrees": [],
            "invalidCandidates": [],
            "complete": False,
        }
        save_report(output, report)

    done_list = (
        [x["key"] for x in report["results"]]
        + [x["key"] for x in report["invalidTrees"]]
        + [x["key"] for x in report["invalidCandidates"]]
    )

    if len(done_list) != len(set(done_list)):
        raise RuntimeError("Duplicate saved results")

    if not set(done_list).issubset(set(keys)):
        raise RuntimeError("Unknown saved result")

    done = set(done_list)
    remaining = [x for x in candidates if x["key"] not in done]

    print("=== MULTI-SWAP EXECUTOR v1.0 ===")
    print("Planned:", len(candidates))
    print("Already processed:", len(done))
    print("Remaining:", len(remaining))
    print("Run limit:", args.limit, flush=True)

    attempted = 0

    for candidate in remaining[:args.limit]:
        if xml_sha256(xml_path) != digest:
            raise RuntimeError("Build XML changed")

        key = candidate["key"]
        removes = candidate["removeIds"]
        adds = candidate["addIds"]

        print(
            f"[{attempted + 1}/{min(args.limit, len(remaining))}] "
            f"{key}",
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
                        f"Unrecognized conflict: {message}"
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
                    f"Unknown PoB error for {key}: {message}"
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
                raise RuntimeError("Removed nodes mismatch")

            if added != sorted(adds):
                raise RuntimeError("Added nodes mismatch")

            if (
                result["passivePointsUsed"]
                != baseline["passivePointsUsed"]
            ):
                raise RuntimeError("Passive point count mismatch")

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
                raise RuntimeError("Unknown constraint status")

            report["results"].append({
                "key": key,
                "removeIds": removes,
                "addIds": adds,
                "status": checked["status"],
                "problems": checked["problems"],
                "changes": checked["changes"],
                "stats": result["stats"],
                "validation": validation,
                "predictedUtility": candidate["predictedUtility"],
                "predictedStatus": candidate["predictedStatus"],
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

        save_report(output, report)
        attempted += 1

    completed = (
        len(report["results"])
        + len(report["invalidTrees"])
        + len(report["invalidCandidates"])
    )

    report["complete"] = completed == len(candidates)
    save_report(output, report)

    print("\n=== MULTI-SWAP SUMMARY ===")
    print("New attempts:", attempted)
    print("Total processed:", completed)
    print("PASS:", sum(
        x["status"] == "PASS" for x in report["results"]
    ))
    print("REJECT:", sum(
        x["status"] == "REJECT" for x in report["results"]
    ))
    print("Invalid trees:", len(report["invalidTrees"]))
    print("Invalid candidates:", len(report["invalidCandidates"]))
    print("Remaining:", len(candidates) - completed)
    print("Saved:", output)


if __name__ == "__main__":
    main()


