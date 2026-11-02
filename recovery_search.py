
# PoE BuildLab — Recovery Search v0.5

import itertools
import os
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
MAX_EXPERIMENTS = 50


def make_key(removes, adds):
    return (
        ",".join(map(str, sorted(removes)))
        + "->"
        + ",".join(map(str, sorted(adds)))
    )

import re


def parse_tree_conflict(message):
    match = re.search(
        r"TREE_CONFLICT\|requested=(\d+)\|disconnected=([\d,]*)",
        message,
    )

    if not match:
        return None

    return {
        "requestedNode": int(match.group(1)),
        "disconnectedNodes": [
            int(value)
            for value in match.group(2).split(",")
            if value
        ],
    }

def main():
    xml_path = Path(os.environ["BUILD_XML"]).resolve()
    xml_hash = xml_sha256(xml_path)
    directory = get_experiment_dir(xml_path, SKILL_GROUP)

    single = load_report(
        directory / "swap_constrained.json",
        xml_path, SKILL_GROUP
    )
    executed = load_report(
        directory / "swap_executed.json",
        xml_path, SKILL_GROUP
    )
    previous = load_report(
        directory / "multi_swap_results.json",
        xml_path, SKILL_GROUP
    )

    if (
        single.get("sourceHashesVerified") is not True
        or executed.get("complete") is not True
        or previous.get("complete") is not True
    ):
        raise RuntimeError("Incomplete or unverified sources")

    if len(executed["results"]) != single["total"]:
        raise RuntimeError("Single-swap count mismatch")

    if len(previous["results"]) + len(previous["rejected"]) != len(previous["candidates"]):
        raise RuntimeError("Previous double-swap results incomplete")

    previously_checked = {
        candidate["key"]
        for candidate in previous["candidates"]
    }

    rows = single["results"]
    candidates = {}

    for a, b in itertools.combinations(rows, 2):
        removes = sorted([a["removeId"], b["removeId"]])
        adds = sorted([a["addId"], b["addId"]])

        if len(set(removes)) != 2 or len(set(adds)) != 2:
            continue

        if set(removes) & set(adds):
            continue

        if a["status"] == "PASS" and b["status"] == "PASS":
            continue

        key = make_key(removes, adds)

        if key in previously_checked:
            continue

        dps = (
            a["changes"]["dps_percent"]
            + b["changes"]["dps_percent"]
        )
        ehp = (
            a["changes"]["ehp_percent"]
            + b["changes"]["ehp_percent"]
        )

        mana = (
            a["changes"]["free_mana_percent"]
            + b["changes"]["free_mana_percent"]
        )

        recharge = (
            a["changes"]["es_recharge_percent"]
            + b["changes"]["es_recharge_percent"]
        )

        regen = (
            a["changes"]["mana_regen_percent"]
            + b["changes"]["mana_regen_percent"]
        )

        # Prioritize estimated overall improvement.
        score = 0.5 * dps + 0.5 * ehp

        # Prefer estimates that can satisfy basic limits.
        predicted_pass = (
            dps >= 0
            and ehp >= 0
            and mana >= -10
            and recharge >= -5
            and regen >= -10
        )

        candidates[key] = {
            "key": key,
            "removeIds": removes,
            "addIds": adds,
            "estimatedScore": score,
            "predictedPass": predicted_pass,
        }

    ordered = sorted(
        candidates.values(),
        key=lambda c: (
            not c["predictedPass"],
            -c["estimatedScore"],
            c["key"],
        )
    )

    selected = ordered[:MAX_EXPERIMENTS]
    output = directory / "recovery_results.json"

    if output.exists():
        report = load_report(
            output, xml_path, SKILL_GROUP
        )
        if (
            report.get("version") not in ("0.5", "0.5.1")
            or report.get("candidates") != selected
        ):
            raise RuntimeError(
                "Saved recovery plan does not match"
            )
    else:
        report = {
            "version": "0.5",
            "xmlPath": str(xml_path),
            "xmlSha256": xml_hash,
            "skillGroup": SKILL_GROUP,
            "available": len(ordered),
            "candidates": selected,
            "results": [],
            "errors": [],
            "complete": False,
        }
        save_report(output, report)

    baseline = executed["baseline"]

    processed_keys = (
        [r["key"] for r in report["results"]]
        + [r["key"] for r in report.get("invalidTrees", [])]
        + [r["key"] for r in report["errors"]]
    )

    if len(processed_keys) != len(set(processed_keys)):
        raise RuntimeError("Duplicate saved recovery results")

    selected_keys = {c["key"] for c in selected}
    if not set(processed_keys).issubset(selected_keys):
        raise RuntimeError("Saved results outside recovery plan")

    processed = set(processed_keys)

    print("=== RECOVERY SEARCH v0.5 ===")
    print("Available:", len(ordered))
    print("Selected:", len(selected))
    print("Already processed:", len(processed))

    try:
        for index, candidate in enumerate(selected, 1):
            key = candidate["key"]

            if key in processed:
                continue

            if xml_sha256(xml_path) != xml_hash:
                raise RuntimeError("Source XML changed")

            print(
                f"[{index}/{len(selected)}] {key}",
                flush=True
            )

            try:
                result = evaluate(
                    xml_path,
                    nodes=candidate["addIds"],
                    remove_nodes=candidate["removeIds"],
                    skill_group=SKILL_GROUP,
                )

                actual_removes = sorted(
                    n["nodeId"]
                    for n in result["removalExperiment"]["nodes"]
                )
                actual_adds = sorted(
                    n["nodeId"]
                    for n in result["passiveExperiment"]["nodes"]
                )

                if (
                    actual_removes != candidate["removeIds"]
                    or actual_adds != candidate["addIds"]
                ):
                    raise ValueError("Node mismatch")

                if result["passivePointsUsed"] != baseline["passivePointsUsed"]:
                    raise ValueError("Passive points changed")

                validation = validate_experiment(
                    baseline, result
                )

                row = {
                    "removeId": ",".join(
                        map(str, candidate["removeIds"])
                    ),
                    "removeName": "Recovery removal",
                    "addId": ",".join(
                        map(str, candidate["addIds"])
                    ),
                    "addName": "Recovery addition",
                    "stats": result["stats"],
                    "validation": validation,
                }

                checked = evaluate_constraints(
                    baseline, row
                )

                report["results"].append({
                    "key": key,
                    "status": checked["status"],
                    "problems": checked["problems"],
                    "changes": checked["changes"],
                    "stats": result["stats"],
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
                    report.setdefault("invalidTrees", []).append({
                        "key": key,
                        **conflict,
                    })

                    print(
                        "  INVALID_TREE",
                        "requested:", conflict["requestedNode"],
                        "disconnected:", conflict["disconnectedNodes"],
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
        print("Interrupted. Progress saved.")
        return

    report["complete"] = len(processed) == len(selected)
    save_report(output, report)

    passed = [
        r for r in report["results"]
        if r["status"] == "PASS"
    ]

    passed.sort(
        key=lambda r: (
            r["changes"]["dps_percent"]
            + r["changes"]["ehp_percent"]
        ),
        reverse=True,
    )

    print("\n=== RECOVERY RESULTS ===")
    print("Complete:", report["complete"])
    print("Calculated:", len(report["results"]))
    print("Errors:", len(report["errors"]))
    print("Invalid trees:", len(report.get("invalidTrees", [])))
    print("Passed:", len(passed))

    for row in passed[:5]:
        c = row["changes"]
        print(
            row["key"],
            f"DPS {c['dps_percent']:+.4f}%",
            f"EHP {c['ehp_percent']:+.4f}%"
        )

    print("Saved:", output)


if __name__ == "__main__":
    main()
