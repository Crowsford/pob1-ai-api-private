
# PoE BuildLab — Multi-Swap Optimizer v0.4
# First stage: evaluate up to 20 double swaps.

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
MAX_EXPERIMENTS = 84
DPS_WEIGHT = 0.5
EHP_WEIGHT = 0.5


def pair_key(remove_ids, add_ids):
    return (
        ",".join(map(str, sorted(remove_ids)))
        + "->"
        + ",".join(map(str, sorted(add_ids)))
    )


def create_candidates(rows):
    candidates = {}

    for first, second in itertools.combinations(rows, 2):
        removes = [first["removeId"], second["removeId"]]
        adds = [first["addId"], second["addId"]]

        # Both removals and additions must be distinct.
        if len(set(removes)) != 2:
            continue

        if len(set(adds)) != 2:
            continue

        # Cannot add and remove the same node.
        if set(removes) & set(adds):
            continue

        removes = sorted(removes)
        adds = sorted(adds)

        key = pair_key(removes, adds)

        estimate_dps = (
            first["changes"]["dps_percent"]
            + second["changes"]["dps_percent"]
        )
        estimate_ehp = (
            first["changes"]["ehp_percent"]
            + second["changes"]["ehp_percent"]
        )

        estimate_score = (
            DPS_WEIGHT * estimate_dps
            + EHP_WEIGHT * estimate_ehp
        )

        candidate = {
            "key": key,
            "removeIds": removes,
            "addIds": adds,
            "estimatedDpsPercent": estimate_dps,
            "estimatedEhpPercent": estimate_ehp,
            "estimatedScore": estimate_score,
        }

        # Keep the same canonical combination only once.
        if (
            key not in candidates
            or estimate_score
            > candidates[key]["estimatedScore"]
        ):
            candidates[key] = candidate

    return sorted(
        candidates.values(),
        key=lambda x: (
            -x["estimatedScore"],
            x["key"],
        ),
    )


def main():
    xml_raw = os.environ.get("BUILD_XML")
    if not xml_raw:
        raise RuntimeError("BUILD_XML is not set")

    xml_path = Path(xml_raw).resolve()
    source_hash = xml_sha256(xml_path)

    directory = get_experiment_dir(
        xml_path, SKILL_GROUP
    )

    constrained = load_report(
        directory / "swap_constrained.json",
        xml_path,
        SKILL_GROUP,
    )

    executed = load_report(
        directory / "swap_executed.json",
        xml_path,
        SKILL_GROUP,
    )

    if constrained.get("sourceHashesVerified") is not True:
        raise RuntimeError("Unverified constraint source")

    if executed.get("complete") is not True:
        raise RuntimeError("Incomplete single-swap experiments")

    rows = [
        row for row in constrained["results"]
        if row["status"] == "PASS"
    ]

    if len(rows) != constrained["passed"]:
        raise RuntimeError("PASS count mismatch")

    candidates = create_candidates(rows)
    selected = candidates[:MAX_EXPERIMENTS]

    output = directory / "multi_swap_results.json"

    if output.exists():
        report = load_report(
            output, xml_path, SKILL_GROUP
        )


        expected_keys = [c["key"] for c in selected]
        saved_keys = [c["key"] for c in report["candidates"]]

        if (
            report.get("version") not in ("0.4", "0.4.1")
            or report.get("weights") != {
                "dps": DPS_WEIGHT,
                "ehp": EHP_WEIGHT,
            }
        ):
            raise RuntimeError(
                "Existing results use incompatible settings"
            )

        # Existing plan must be an exact prefix of the new plan.
        if saved_keys != expected_keys[:len(saved_keys)]:
            raise RuntimeError(
                "Existing plan is not a prefix of the new plan"
            )

        # Previously processed combinations must be unique
        # and belong to the saved plan.
        processed_keys = [
            r["key"] for r in report["results"]
        ] + [
            r["key"] for r in report["rejected"]
        ]

        if (
            len(processed_keys) != len(set(processed_keys))
            or not set(processed_keys).issubset(set(saved_keys))
        ):
            raise RuntimeError(
                "Invalid or duplicate previous results"
            )

        # Extend the plan without deleting previous results.
        if len(selected) > len(saved_keys):
            print(
                f"[Extend] {len(saved_keys)} -> "
                f"{len(selected)} experiments"
            )

            report["candidates"] = selected
            report["availableCombinations"] = len(candidates)
            report["version"] = "0.4.1"
            report["complete"] = False

            save_report(output, report)

        print("[Resume] Loading previous results")


    else:
        report = {
            "version": "0.4",
            "xmlPath": str(xml_path),
            "xmlSha256": source_hash,
            "skillGroup": SKILL_GROUP,
            "weights": {
                "dps": DPS_WEIGHT,
                "ehp": EHP_WEIGHT,
            },
            "availableCombinations": len(candidates),
            "candidates": selected,
            "baseline": executed["baseline"],
            "results": [],
            "rejected": [],
            "complete": False,
        }

        save_report(output, report)

    baseline = report["baseline"]

    processed = {
        row["key"] for row in report["results"]
    } | {
        row["key"] for row in report["rejected"]
    }

    print("=== MULTI-SWAP OPTIMIZER v0.4 ===")
    print("Available combinations:", len(candidates))
    print("Selected experiments:", len(selected))
    print("Already processed:", len(processed))

    try:
        for index, candidate in enumerate(selected, 1):
            key = candidate["key"]

            if key in processed:
                continue

            if xml_sha256(xml_path) != source_hash:
                raise RuntimeError(
                    "Source XML changed during optimization"
                )

            print(
                f"[{index}/{len(selected)}] {key}",
                flush=True,
            )

            removes = candidate["removeIds"]
            adds = candidate["addIds"]

            try:
                result = evaluate(
                    xml_path,
                    nodes=adds,
                    remove_nodes=removes,
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

                if actual_removes != removes:
                    raise ValueError("Unexpected removed nodes")

                if actual_adds != adds:
                    raise ValueError("Unexpected added nodes")

                if (
                    result["passivePointsUsed"]
                    != baseline["passivePointsUsed"]
                ):
                    raise ValueError(
                        "Passive point count changed"
                    )

                validation = validate_experiment(
                    baseline, result
                )

                row = {
                    "removeId": ",".join(map(str, removes)),
                    "removeName": "Double removal",
                    "addId": ",".join(map(str, adds)),
                    "addName": "Double addition",
                    "stats": result["stats"],
                    "validation": validation,
                }

                constraints = evaluate_constraints(
                    baseline, row
                )

                changes = constraints["changes"]

                score = (
                    DPS_WEIGHT * changes["dps_percent"]
                    + EHP_WEIGHT * changes["ehp_percent"]
                )

                report["results"].append({
                    "key": key,
                    "removeIds": removes,
                    "addIds": adds,
                    "status": constraints["status"],
                    "problems": constraints["problems"],
                    "changes": changes,
                    "score": score,
                    "stats": result["stats"],
                    "validation": validation,
                })

                print(
                    f"  {constraints['status']} | "
                    f"DPS {changes['dps_percent']:+.4f}% | "
                    f"EHP {changes['ehp_percent']:+.4f}%",
                    flush=True,
                )

            except Exception as exc:
                report["rejected"].append({
                    "key": key,
                    "error": str(exc),
                })
                print(
                    f"  ERROR: {exc}",
                    flush=True,
                )

            if xml_sha256(xml_path) != source_hash:
                raise RuntimeError(
                    "Source XML changed during calculation"
                )

            save_report(output, report)
            processed.add(key)

    except KeyboardInterrupt:
        print("\nInterrupted. Results saved for resuming.")
        return

    if xml_sha256(xml_path) != source_hash:
        raise RuntimeError("Source XML changed")

    report["complete"] = (
        len(processed) == len(selected)
    )
    save_report(output, report)

    passed = [
        row for row in report["results"]
        if row["status"] == "PASS"
    ]

    passed.sort(
        key=lambda row: row["score"],
        reverse=True,
    )

    print("\n=== RESULTS ===")
    print("Completed:", report["complete"])
    print("Calculated:", len(report["results"]))
    print("Calculation errors:", len(report["rejected"]))
    print("Passed constraints:", len(passed))

    print("\n=== TOP 5 DOUBLE SWAPS ===")
    for row in passed[:5]:
        print(
            f"{row['key']} | "
            f"DPS {row['changes']['dps_percent']:+.4f}% | "
            f"EHP {row['changes']['ehp_percent']:+.4f}% | "
            f"Score {row['score']:+.4f}"
        )

    print("\nSaved:", output)


if __name__ == "__main__":
    main()
