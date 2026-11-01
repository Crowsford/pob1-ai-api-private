
# PoE BuildLab — Build Comparison v0.2

import argparse
import json
import math
import sys

from experiment_runner import evaluate


def compare(xml_path, level=None, node=None):
    if (level is None) == (node is None):
        raise ValueError("Specify exactly one: --level or --node")

    # Evaluate the original build without modifications.
    baseline = evaluate(xml_path)

    # Evaluate the same build with one modification.
    modified = evaluate(xml_path, level=level, node=node)

    changes = {}

    for stat, before in baseline["stats"].items():
        after = modified["stats"].get(stat)

        if (
            isinstance(before, bool)
            or isinstance(after, bool)
            or not isinstance(before, (int, float))
            or not isinstance(after, (int, float))
            or not math.isfinite(before)
            or not math.isfinite(after)
        ):
            continue

        delta = after - before

        percent = (
            delta / abs(before) * 100
            if before != 0
            else None
        )

        changes[stat] = {
            "before": before,
            "after": after,
            "delta": round(delta, 6),
            "percent": round(percent, 2)
            if percent is not None
            else None,
        }

    result = {
        "ok": True,
        "experiment": (
            "passive_node_allocation"
            if node is not None
            else "character_level_change"
        ),
        "baselineLevel": baseline["level"],
        "modifiedLevel": modified["level"],
        "changes": changes,
    }

    if node is not None:
        experiment = modified.get("passiveExperiment")

        if not isinstance(experiment, dict):
            raise RuntimeError(
                "PoB did not return passive experiment metadata"
            )

        result["passiveExperiment"] = experiment

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Compare PoE builds using headless Path of Building"
    )

    parser.add_argument(
        "xml_path",
        help="Path to the source build XML",
    )

    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument(
        "--level",
        type=int,
        help="Evaluate a different character level",
    )

    group.add_argument(
        "--node",
        type=int,
        help="Allocate a passive tree node by ID",
    )

    args = parser.parse_args()

    try:
        result = compare(
            args.xml_path,
            level=args.level,
            node=args.node,
        )

        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
