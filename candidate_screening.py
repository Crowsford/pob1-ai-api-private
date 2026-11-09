
# PoE BuildLab AI — Candidate Screening v0.2
# Discover new removals automatically and test them
# against previously tested additions.

import json
import os
import subprocess
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
from recovery_search import parse_tree_conflict

SKILL_GROUP = 6
VERSION = "0.2"


def discover_candidates(xml_path):
    src_dir = Path(__file__).resolve().parent / "src"

    process = subprocess.run(
        ["luajit", "passive_candidates.lua", str(xml_path)],
        cwd=src_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if process.returncode != 0:
        raise RuntimeError(
            "Candidate discovery failed:\n"
            + process.stdout[-1000:]
            + "\n"
            + process.stderr[-2000:]
        )

    for line in process.stdout.splitlines():
        if line.startswith("RESULT_JSON:"):
            data = json.loads(line[len("RESULT_JSON:"):])

            if data.get("ok") is not True:
                raise RuntimeError("Discovery returned invalid data")

            if (
                len(data["removalCandidates"])
                != data["removalCandidateCount"]
            ):
                raise RuntimeError("Removal candidate count mismatch")

            return data

    raise RuntimeError("RESULT_JSON missing from discovery")


def main():
    raw = os.environ.get("BUILD_XML")

    if not raw:
        raise RuntimeError("BUILD_XML is not set")

    xml_path = Path(raw).resolve()
    xml_hash = xml_sha256(xml_path)
    directory = get_experiment_dir(xml_path, SKILL_GROUP)

    previous = load_report(
        directory / "swap_constrained.json",
        xml_path,
        SKILL_GROUP,
    )

    executed = load_report(
        directory / "swap_executed.json",
        xml_path,
        SKILL_GROUP,
    )

    baseline = executed["baseline"]

    if not executed.get("complete"):
        raise RuntimeError("Previous screening is incomplete")

    if baseline["stats"]["combinedDPS"] <= 0:
        raise RuntimeError("Invalid baseline DPS")

    discovered = discover_candidates(xml_path)

    if discovered["pointsUsed"] != baseline["passivePointsUsed"]:
        raise RuntimeError("Discovery baseline point mismatch")

    old_removals = {
        int(row["removeId"])
        for row in previous["results"]
    }

    old_additions = {
        int(row["addId"])
        for row in previous["results"]
    }

    known_removals = {
        int(node["id"]): node["name"]
        for node in discovered["removalCandidates"]
    }

    known_additions = {
        int(node["id"]): node["name"]
        for node in discovered["candidates"]
    }

    new_removals = sorted(
        set(known_removals) - old_removals
    )

    additions = sorted(old_additions)

    if not set(additions).issubset(known_additions):
        raise RuntimeError("Previously tested addition is missing")

    candidates = []

    for remove_id in new_removals:
        for add_id in additions:
            if remove_id == add_id:
                continue

            candidates.append({
                "key": f"{remove_id}->{add_id}",
                "removeId": remove_id,
                "removeName": known_removals[remove_id],
                "addId": add_id,
                "addName": known_additions[add_id],
            })

    output = directory / "candidate_screening_v02.json"

    if output.exists():
        report = load_report(
            output, xml_path, SKILL_GROUP
        )

        if (
            report.get("version") != VERSION
            or report.get("candidates") != candidates
            or report.get("xmlSha256") != xml_hash
        ):
            raise RuntimeError("Saved screening plan mismatch")

        print("[Resume] Existing report loaded")

    else:
        report = {
            "version": VERSION,
            "xmlPath": str(xml_path),
            "xmlSha256": xml_hash,
            "skillGroup": SKILL_GROUP,
            "baseline": baseline,
            "newRemovals": new_removals,
            "additions": additions,
            "candidates": candidates,
            "results": [],
            "invalidTrees": [],
            "errors": [],
            "complete": False,
        }

        save_report(output, report)

    processed_list = (
        [row["key"] for row in report["results"]]
        + [row["key"] for row in report["invalidTrees"]]
        + [row["key"] for row in report["errors"]]
    )

    planned_keys = {row["key"] for row in candidates}

    if (
        len(processed_list) != len(set(processed_list))
        or not set(processed_list).issubset(planned_keys)
    ):
        raise RuntimeError("Invalid saved screening results")

    processed = set(processed_list)

    print("=== CANDIDATE SCREENING v0.2 ===")
    print("Discovered removal candidates:", len(known_removals))
    print("New removals:", new_removals)
    print("Previously tested additions:", len(additions))
    print("Planned experiments:", len(candidates))
    print("Already processed:", len(processed))

    try:
        for index, candidate in enumerate(candidates, 1):
            key = candidate["key"]

            if key in processed:
                continue

            if xml_sha256(xml_path) != xml_hash:
                raise RuntimeError("Source XML changed")

            print(
                f"[{index}/{len(candidates)}] {key}",
                flush=True,
            )

            try:
                result = evaluate(
                    xml_path,
                    nodes=[candidate["addId"]],
                    remove_nodes=[candidate["removeId"]],
                    skill_group=SKILL_GROUP,
                )

                removed = [
                    node["nodeId"]
                    for node in result["removalExperiment"]["nodes"]
                ]
                added = [
                    node["nodeId"]
                    for node in result["passiveExperiment"]["nodes"]
                ]

                if removed != [candidate["removeId"]]:
                    raise ValueError("Unexpected removed node")

                if added != [candidate["addId"]]:
                    raise ValueError("Unexpected added node")

                if (
                    result["passivePointsUsed"]
                    != baseline["passivePointsUsed"]
                ):
                    raise ValueError("Passive point count changed")

                validation = validate_experiment(
                    baseline, result
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

                report["results"].append({
                    "key": key,
                    "removeId": candidate["removeId"],
                    "removeName": candidate["removeName"],
                    "addId": candidate["addId"],
                    "addName": candidate["addName"],
                    "status": checked["status"],
                    "problems": checked["problems"],
                    "changes": checked["changes"],
                    "stats": result["stats"],
                    "validation": validation,
                })

                print(
                    " ",
                    checked["status"],
                    checked["problems"],
                    flush=True,
                )

            except Exception as exc:
                conflict = parse_tree_conflict(str(exc))

                if conflict is not None:
                    report["invalidTrees"].append({
                        "key": key,
                        **conflict,
                    })

                    print(
                        "  INVALID_TREE",
                        conflict["disconnectedNodes"],
                        flush=True,
                    )
                else:
                    report["errors"].append({
                        "key": key,
                        "error": str(exc),
                    })

                    print("  ERROR:", exc, flush=True)

            if xml_sha256(xml_path) != xml_hash:
                raise RuntimeError("Source XML changed")

            save_report(output, report)
            processed.add(key)

    except KeyboardInterrupt:
        print("Interrupted. Completed results saved.")
        return

    report["complete"] = len(processed) == len(candidates)
    save_report(output, report)

    passed = [
        row for row in report["results"]
        if row["status"] == "PASS"
    ]

    passed.sort(
        key=lambda row: (
            row["changes"]["dps_percent"]
            + row["changes"]["ehp_percent"]
        ),
        reverse=True,
    )

    print("\n=== SCREENING RESULTS ===")
    print("Complete:", report["complete"])
    print("Calculated:", len(report["results"]))
    print("Passed:", len(passed))
    print("Invalid trees:", len(report["invalidTrees"]))
    print("Other errors:", len(report["errors"]))

    print("\nTOP 5:")
    for row in passed[:5]:
        changes = row["changes"]

        print(
            row["key"],
            f"DPS {changes['dps_percent']:+.4f}%",
            f"EHP {changes['ehp_percent']:+.4f}%",
        )

    print("Saved:", output)


if __name__ == "__main__":
    main()
