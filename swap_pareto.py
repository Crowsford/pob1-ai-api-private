
# PoE BuildLab — Swap Pareto Analysis v0.2

import argparse
import json
import math
from pathlib import Path

METRICS = ("combinedDPS", "totalEHP")
TOLERANCE = 1e-6


def metric(row, name):
    value = row["stats"][name]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Invalid metric {name}: {value}")
    if not math.isfinite(value):
        raise ValueError(f"Non-finite metric {name}")
    return float(value)


def dominates(a, b):
    values_a = [metric(a, name) for name in METRICS]
    values_b = [metric(b, name) for name in METRICS]

    return (
        all(
            x >= y - TOLERANCE
            for x, y in zip(values_a, values_b)
        )
        and any(
            x > y + TOLERANCE
            for x, y in zip(values_a, values_b)
        )
    )


def is_eligible(row, baseline, min_mana):
    validation = row.get("validation", {})

    if validation.get("status") != "VALID":
        return False

    regression = validation.get("attributeRegression", {})
    if regression.get("status") != "NO_REGRESSION":
        return False

    stats = row["stats"]
    base = baseline["stats"]

    # First-pass protective constraints.
    for name in (
        "fireResist",
        "coldResist",
        "lightningResist",
        "chaosResist",
    ):
        if metric({"stats": stats}, name) + TOLERANCE < metric(
            {"stats": base}, name
        ):
            return False

    mana = stats.get("manaUnreserved")
    cost = stats.get("manaCost")

    if not all(
        isinstance(x, (int, float)) and math.isfinite(x)
        for x in (mana, cost)
    ):
        return False

    if mana < max(cost, min_mana):
        return False

    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file")
    parser.add_argument("--min-mana", type=float, default=0)
    parser.add_argument(
        "--output",
        default="swap_pareto_results.json",
    )
    args = parser.parse_args()

    data = json.loads(
        Path(args.input_file).read_text(encoding="utf-8")
    )

    baseline = data["baseline"]
    pairs = data["results"]

    if not pairs:
        raise ValueError("No calculated swaps")

    eligible = [
        row for row in pairs
        if is_eligible(row, baseline, args.min_mana)
    ]

    frontier = [
        row for row in eligible
        if not any(
            dominates(other, row)
            for other in eligible
            if other is not row
        )
    ]

    frontier.sort(
        key=lambda row: (
            -metric(row, "combinedDPS"),
            -metric(row, "totalEHP"),
            row["removeId"],
            row["addId"],
        )
    )

    results = []

    for row in frontier:
        stats = row["stats"]
        base = baseline["stats"]

        results.append({
            "removeId": row["removeId"],
            "removeName": row["removeName"],
            "addId": row["addId"],
            "addName": row["addName"],
            "dpsGainPercent": row["dpsGainPercent"],
            "ehpChange": row["ehpChange"],
            "energyShieldChange": (
                stats["energyShield"] - base["energyShield"]
            ),
            "esRechargeChange": (
                stats["energyShieldRecharge"]
                - base["energyShieldRecharge"]
            ),
            "esRegenChange": (
                stats["energyShieldRegen"]
                - base["energyShieldRegen"]
            ),
            "manaRegenChange": (
                stats["manaRegen"] - base["manaRegen"]
            ),
            "manaUnreserved": stats["manaUnreserved"],
        })

    report = {
        "version": "0.2",
        "sourceFile": str(args.input_file),
        "comparedMetrics": list(METRICS),
        "minimumMana": args.min_mana,
        "calculated": len(pairs),
        "eligible": len(eligible),
        "paretoCount": len(results),
        "paretoFrontier": results,
    }

    Path(args.output).write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Calculated: {len(pairs)}")
    print(f"Eligible: {len(eligible)}")
    print(f"Pareto variants: {len(results)}")
    print("\n=== PARETO FRONTIER ===")

    for item in results:
        print(
            f"{item['removeId']} -> {item['addId']}: "
            f"DPS {item['dpsGainPercent']:+.4f}%, "
            f"EHP {item['ehpChange']:+.2f}, "
            f"ES recharge {item['esRechargeChange']:+.2f}, "
            f"Mana regen {item['manaRegenChange']:+.2f}, "
            f"Free mana {item['manaUnreserved']}"
        )

    print(f"\nSaved: {args.output}")


if __name__ == "__main__":
    main()
