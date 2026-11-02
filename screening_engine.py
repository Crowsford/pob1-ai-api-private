
# PoE BuildLab AI — Screening Engine v0.6
# Automatic discovery, historical import, resumable experiments.

import argparse
import json
import os
import re
import subprocess
from collections import Counter
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


VERSION = "0.4"
SKILL_GROUP = 6
SOURCES = (
    "swap_constrained.json",
    "candidate_screening_v02.json",
    "candidate_screening_v03.json",
)


def discover(xml_path):
    root = Path(__file__).resolve().parent

    proc = subprocess.run(
        ["luajit", "passive_candidates.lua", str(xml_path)],
        cwd=root / "src",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if proc.returncode:
        raise RuntimeError(
            f"Lua discovery failed:\n{proc.stdout[-1500:]}\n"
            f"{proc.stderr[-1500:]}"
        )

    for line in proc.stdout.splitlines():
        if line.startswith("RESULT_JSON:"):
            data = json.loads(line[len("RESULT_JSON:"):])
            if data.get("ok") is not True:
                raise RuntimeError("Invalid discovery result")
            return data

    raise RuntimeError("RESULT_JSON not found")


def key_of(row):
    return f"{int(row['removeId'])}->{int(row['addId'])}"


def build_plan(data):
    removals = data["removalCandidates"]
    additions = data["candidates"]

    if len(removals) != data["removalCandidateCount"]:
        raise RuntimeError("Removal count mismatch")

    if len(additions) != data["candidateCount"]:
        raise RuntimeError("Addition count mismatch")

    if len({int(n["id"]) for n in removals}) != len(removals):
        raise RuntimeError("Duplicate removal ID")

    if len({int(n["id"]) for n in additions}) != len(additions):
        raise RuntimeError("Duplicate addition ID")

    plan = []

    for rem in removals:
        for add in additions:
            rid = int(rem["id"])
            aid = int(add["id"])

            if rid == aid:
                continue

            plan.append({
                "key": f"{rid}->{aid}",
                "removeId": rid,
                "removeName": rem["name"],
                "addId": aid,
                "addName": add["name"],
            })

    return sorted(
        plan,
        key=lambda x: (x["removeId"], x["addId"]),
    )



def load_history(directory, xml_path):
    history = {}
    counts = {}

    for filename in SOURCES:
        report = load_report(
            directory / filename, xml_path, SKILL_GROUP
        )

        rows = report["results"]

        if filename == "swap_constrained.json":
            # Legacy constraint report has no "complete" field.
            total = report.get("total")

            if total != len(rows):
                raise RuntimeError(
                    f"Incomplete legacy history: {filename}. "
                    f"Expected {total}, got {len(rows)}"
                )

            if report.get("passed", 0) + report.get("rejected", 0) != total:
                raise RuntimeError(
                    f"Invalid legacy status counts: {filename}"
                )

        else:
            if report.get("complete") is not True:
                raise RuntimeError(
                    f"Incomplete history: {filename}"
                )

            if report.get("errors"):
                raise RuntimeError(
                    f"Unresolved errors in history: {filename}"
                )

            expected = len(report["candidates"])

            if (
                len(rows) + len(report.get("invalidTrees", []))
                != expected
            ):
                raise RuntimeError(
                    f"History count mismatch: {filename}"
                )

            if report.get("invalidTrees"):
                raise RuntimeError(
                    f"Historical tree conflicts require import: {filename}"
                )

        counts[filename] = len(rows)

        for row in rows:
            key = key_of(row)

            if key in history:
                raise RuntimeError(
                    f"Duplicate historical experiment: {key}"
                )

            if row.get("status") not in ("PASS", "REJECT"):
                raise RuntimeError(
                    f"Invalid historical status for {key}"
                )

            history[key] = {
                "source": filename,
                "status": row["status"],
            }

    return history, counts



def verify_result(baseline, result, candidate):
    removed = [
        int(x["nodeId"])
        for x in result["removalExperiment"]["nodes"]
    ]
    added = [
        int(x["nodeId"])
        for x in result["passiveExperiment"]["nodes"]
    ]

    if removed != [candidate["removeId"]]:
        raise RuntimeError("Unexpected removed node")

    if added != [candidate["addId"]]:
        raise RuntimeError("Unexpected added node")

    if result["passivePointsUsed"] != baseline["passivePointsUsed"]:
        raise RuntimeError("Passive point count changed")

    return validate_experiment(baseline, result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit", type=int, default=10,
        help="Maximum NEW evaluations in this run",
    )

    parser.add_argument(
        "--queue",
        action="store_true",
        help="Use adaptive_queue.json experiment order",
    )

    args = parser.parse_args()

    if args.limit < 1:
        raise RuntimeError("--limit must be positive")

    raw = os.environ.get("BUILD_XML")
    if not raw:
        raise RuntimeError("BUILD_XML is not set")

    xml_path = Path(raw).resolve()
    xml_hash = xml_sha256(xml_path)

    directory = get_experiment_dir(
        xml_path, SKILL_GROUP
    )

    executed = load_report(
        directory / "swap_executed.json",
        xml_path,
        SKILL_GROUP,
    )

    if executed.get("complete") is not True:
        raise RuntimeError("Original swap execution incomplete")

    baseline = executed["baseline"]

    if baseline["stats"]["combinedDPS"] <= 0:
        raise RuntimeError("Invalid baseline DPS")

    discovered = discover(xml_path)

    if discovered["pointsUsed"] != baseline["passivePointsUsed"]:
        raise RuntimeError("Discovery points mismatch")

    if xml_sha256(xml_path) != xml_hash:
        raise RuntimeError("XML changed during discovery")

    plan = build_plan(discovered)
    plan_keys = {x["key"] for x in plan}

    history, counts = load_history(directory, xml_path)

    unknown = set(history) - plan_keys
    if unknown:
        raise RuntimeError(
            f"Historical pairs missing from current plan: "
            f"{sorted(unknown)[:5]}"
        )

    output = directory / "screening_engine.json"

    if output.exists():
        report = load_report(
            output, xml_path, SKILL_GROUP
        )

        if (
            report.get("version") != VERSION
            or report.get("xmlSha256") != xml_hash
            or report.get("plan") != plan
        ):
            raise RuntimeError(
                "Saved engine report is incompatible"
            )
    else:
        report = {
            "version": VERSION,
            "xmlPath": str(xml_path),
            "xmlSha256": xml_hash,
            "skillGroup": SKILL_GROUP,
            "plan": plan,
            "historySources": counts,
            "results": [],
            "invalidTrees": [],
            "invalidCandidates": [],
            "complete": False,
        }
        save_report(output, report)

    calculated = {
        x["key"] for x in report["results"]
    }
    invalid = {
        x["key"] for x in report["invalidTrees"]
    }

    invalid_candidates = {
        x["key"] for x in report.get("invalidCandidates", [])
    }

    all_saved = [
        x["key"] for x in report["results"]
    ] + [
        x["key"] for x in report["invalidTrees"]
    ] + [
    x["key"] for x in report.get("invalidCandidates", [])
    ]

    if len(all_saved) != len(set(all_saved)):
        raise RuntimeError("Duplicate saved engine results")

    if not set(all_saved).issubset(plan_keys):
        raise RuntimeError("Unknown saved experiment")

    if set(all_saved) & set(history):
        raise RuntimeError(
            "Engine repeats a historical experiment"
        )

    done = set(history) | calculated | invalid | invalid_candidates
    remaining = [x for x in plan if x["key"] not in done]







    if args.queue:
        queue_file = directory / "adaptive_queue.json"
        queue_data = json.loads(
            queue_file.read_text(encoding="utf-8")
        )

        if (
            queue_data.get("xmlSha256") != xml_hash
            or queue_data.get("skillGroup") != SKILL_GROUP
            or queue_data.get("version") != "0.6"
        ):
            raise RuntimeError("Adaptive queue metadata mismatch")

        queued_keys = [
            item["key"] for item in queue_data["queue"]
        ]

        if len(queued_keys) != len(set(queued_keys)):
            raise RuntimeError("Duplicate keys in adaptive queue")

        remaining_by_key = {
            item["key"]: item for item in remaining
        }

        unknown = set(queued_keys) - plan_keys
        if unknown:
            raise RuntimeError("Adaptive queue contains unknown keys")

        # Previously completed keys may appear in the queue
        # after an interrupted or partial engine run.
        remaining = [
            remaining_by_key[key]
            for key in queued_keys
            if key in remaining_by_key
        ]

        if len(remaining) != len(remaining_by_key):
            raise RuntimeError(
                "Adaptive queue does not cover all remaining pairs. "
                "Regenerate adaptive_queue.json."
            )






    print("=== SCREENING ENGINE v0.4 ===")
    print("Removals:", discovered["removalCandidateCount"])
    print("Additions:", discovered["candidateCount"])
    print("Total combinations:", len(plan))
    print("Historical combinations:", len(history))
    print("New calculated:", len(calculated))
    print("Invalid trees:", len(invalid))
    print("Remaining:", len(remaining))
    print("Current run limit:", args.limit, flush=True)

    attempted = 0

    for candidate in remaining[:args.limit]:
        if xml_sha256(xml_path) != xml_hash:
            raise RuntimeError("Source XML changed")

        key = candidate["key"]
        print(
            f"[{attempted + 1}/{min(args.limit, len(remaining))}] "
            f"{key}",
            flush=True,
        )

        try:
            result = evaluate(
                xml_path,
                nodes=[candidate["addId"]],
                remove_nodes=[candidate["removeId"]],
                skill_group=SKILL_GROUP,
            )

        except Exception as exc:
            message = str(exc)

            # Only known tree topology conflicts are terminal
            # candidate outcomes. Other errors stop execution.
            if "Node requires more than one point:" in message:
                report.setdefault("invalidCandidates", []).append({
                    "key": key,
                    "reason": "MULTI_POINT_REQUIRED",
                    "error": message.splitlines()[0],
                })
                print("  INVALID_CANDIDATE: MULTI_POINT_REQUIRED", flush=True)

            elif "TREE_CONFLICT|" in message:
                match = re.search(
                    r"TREE_CONFLICT\|requested=(\d+)"
                    r"\|disconnected=([0-9,]+)",
                    message,
                )

                if not match:
                    raise RuntimeError(
                        f"Unrecognized tree conflict: {message}"
                    ) from exc

                report["invalidTrees"].append({
                    "key": key,
                    "requested": int(match.group(1)),
                    "disconnected": [
                        int(x) for x in match.group(2).split(",")
                    ],
                })
                print("  INVALID_TREE", flush=True)

            else:
                raise RuntimeError(
                    f"Evaluation failed for {key}: {message}"
                ) from exc

        else:
            validation = verify_result(
                baseline, result, candidate
            )

            row = {
                "removeId": candidate["removeId"],
                "removeName": candidate["removeName"],
                "addId": candidate["addId"],
                "addName": candidate["addName"],
                "stats": result["stats"],
                "validation": validation,
            }

            checked = evaluate_constraints(
                baseline, row
            )

            status = checked["status"]

            if status not in ("PASS", "REJECT"):
                raise RuntimeError(
                    f"Unexpected constraint status: {status}"
                )

            report["results"].append({
                "key": key,
                **row,
                "status": status,
                "problems": checked["problems"],
                "changes": checked["changes"],
            })

            print(
                " ", status,
                checked["problems"],
                flush=True,
            )

        if xml_sha256(xml_path) != xml_hash:
            raise RuntimeError("Source XML changed")

        save_report(output, report)
        attempted += 1

    completed = (
        len(history)
        + len(report["results"])
        + len(report["invalidTrees"])
        + len(report.get("invalidCandidates", []))
    )

    report["complete"] = completed == len(plan)
    save_report(output, report)

    statuses = Counter(
        row["status"] for row in report["results"]
    )

    print("\n=== ENGINE SUMMARY ===")
    print("Evaluated this run:", attempted)
    print("Total completed:", completed, "/", len(plan))
    print("Remaining:", len(plan) - completed)
    print("New PASS:", statuses["PASS"])
    print("New REJECT:", statuses["REJECT"])
    print("Invalid trees:", len(report["invalidTrees"]))
    print("Complete:", report["complete"])
    print("Saved:", output)
    print("Invalid candidates:", len(report.get("invalidCandidates", [])))


if __name__ == "__main__":
    main()
