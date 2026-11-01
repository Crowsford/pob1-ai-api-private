
# PoE BuildLab — Build Comparison v0.3

import argparse
import json
import math
import sys

from experiment_runner import evaluate, parse_nodes


def numeric(value):
    return (
        type(value) in (int, float)
        and math.isfinite(value)
    )


def calculate_changes(before_stats, after_stats):
    changes = {}

    for stat, before in before_stats.items():
        after = after_stats.get(stat)

        if not numeric(before) or not numeric(after):
            continue

        delta = after - before
        percent = (
            delta / abs(before) * 100
            if before != 0 else None
        )

        changes[stat] = {
            "before": before,
            "after": after,
            "delta": round(delta, 6),
            "percent": round(percent, 3)
            if percent is not None else None,
        }

    return changes


def validate_experiment(result, expected_nodes):
    experiment = result.get("passiveExperiment")

    if not isinstance(experiment, dict):
        raise RuntimeError("Missing passive experiment metadata")

    actual_nodes = [
        item["nodeId"]
        for item in experiment.get("nodes", [])
    ]

    if actual_nodes != expected_nodes:
        raise RuntimeError(
            f"Unexpected allocated nodes: {actual_nodes}"
        )

    if experiment.get("pointsSpent") != len(expected_nodes):
        raise RuntimeError("Unexpected passive point cost")

    return experiment


def compare(xml_path, level=None, node=None, nodes=None):
    if node is not None and nodes is not None:
        raise ValueError("Use either --node or --nodes")

    selected = (
        [node] if node is not None
        else list(nodes) if nodes is not None
        else []
    )

    if level is None and not selected:
        raise ValueError("Specify --level, --node or --nodes")

    baseline = evaluate(xml_path)

    modified = evaluate(
        xml_path,
        level=level,
        nodes=selected if selected else None,
    )

    result = {
        "ok": True,
        "experiment": (
            "passive_node_combination"
            if len(selected) > 1
            else "passive_node_allocation"
            if selected
            else "character_level_change"
        ),
        "baselineLevel": baseline["level"],
        "modifiedLevel": modified["level"],
        "changes": calculate_changes(
            baseline["stats"],
            modified["stats"],
        ),
    }

    if not selected:
        return result

    result["passiveExperiment"] = validate_experiment(
        modified, selected
    )

    # Synergy is only meaningful when the character level
    # is unchanged across all experiments.
    if modified["level"] != baseline["level"]:
        result["synergy"] = None
        result["synergyNote"] = (
            "Synergy not calculated when changing level"
        )
        return result

    if len(selected) == 1:
        return result

    individual = []

    for node_id in selected:
        single = evaluate(xml_path, node=node_id)
        validate_experiment(single, [node_id])

        individual.append({
            "nodeId": node_id,
            "changes": calculate_changes(
                baseline["stats"],
                single["stats"],
            ),
        })

    synergy = {}

    for stat, combined_change in result["changes"].items():
        individual_deltas = []

        for experiment in individual:
            change = experiment["changes"].get(stat)

            if change is None:
                break

            individual_deltas.append(change["delta"])

        if len(individual_deltas) != len(individual):
            continue

        # Calculate with full-precision individual values.
        summed_delta = sum(
            experiment["changes"][stat]["after"]
            - experiment["changes"][stat]["before"]
            for experiment in individual
        )

        combined_delta = (
            combined_change["after"]
            - combined_change["before"]
        )

        interaction = combined_delta - summed_delta

        synergy[stat] = {
            "sumOfIndividualDeltas": round(
                summed_delta, 6
            ),
            "combinedDelta": round(
                combined_delta, 6
            ),
            "interaction": round(
                interaction, 6
            ),
        }

    result["individualExperiments"] = individual
    result["synergy"] = synergy

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Compare PoE builds and passive combinations"
    )

    parser.add_argument("xml_path")

    parser.add_argument(
        "--level",
        type=int,
        default=None,
    )

    group = parser.add_mutually_exclusive_group()

    group.add_argument("--node", type=int)

    group.add_argument(
        "--nodes",
        type=parse_nodes,
        help="Comma-separated passive node IDs",
    )

    parser.add_argument(
        "--output",
        help="Save results to a JSON file",
    )

    args = parser.parse_args()

    try:
        result = compare(
            args.xml_path,
            level=args.level,
            node=args.node,
            nodes=args.nodes,
        )

        output = json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )

        if args.output:
            from pathlib import Path
            Path(args.output).write_text(
                output + "\n",
                encoding="utf-8",
            )
        else:
            print(output)

        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
