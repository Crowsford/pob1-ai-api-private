
# PoE BuildLab — Pareto Analysis v0.1

import argparse
import json
import sys
from pathlib import Path


def dominates(a, b):
    """True if a is at least as good as b in both metrics,
    and strictly better in at least one."""
    return (
        a["gain"] >= b["gain"]
        and a["defense"]["totalEHP"] >= b["defense"]["totalEHP"]
        and (
            a["gain"] > b["gain"]
            or a["defense"]["totalEHP"] > b["defense"]["totalEHP"]
        )
    )


def analyze(data, min_ehp=None):
    pairs = data.get("allPairs", data.get("topPairs", []))

    eligible = [
        pair for pair in pairs
        if pair["defense"]["totalEHP"] is not None
        and (min_ehp is None
             or pair["defense"]["totalEHP"] >= min_ehp)
    ]

    frontier = [
        pair for pair in eligible
        if not any(
            dominates(other, pair)
            for other in eligible
            if other is not pair
        )
    ]

    frontier.sort(
        key=lambda p: (
            -p["gain"],
            -p["defense"]["totalEHP"],
        )
    )

    return {
        "evaluated": len(pairs),
        "eligible": len(eligible),
        "paretoCount": len(frontier),
        "paretoFrontier": [
            {
                "nodes": [n["id"] for n in pair["nodes"]],
                "gainPercent": pair["gainPercent"],
                "gainDPS": pair["gain"],
                "totalEHP": pair["defense"]["totalEHP"],
                "energyShield": pair["defense"]["energyShield"],
            }
            for pair in frontier
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("results_file")
    parser.add_argument("--min-ehp", type=float)
    args = parser.parse_args()

    try:
        path = Path(args.results_file)
        data = json.loads(path.read_text(encoding="utf-8"))

        result = analyze(data, args.min_ehp)
        print(json.dumps(
            result, ensure_ascii=False, indent=2
        ))
        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
