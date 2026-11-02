
# PoE BuildLab — Constraint-Aware Ranker v0.2

import argparse
import json
from pathlib import Path

SOURCE = Path("swap_constrained.json")
OUTPUT = Path("constraint_ranked.json")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dps-weight", type=float, default=0.5
    )
    parser.add_argument(
        "--ehp-weight", type=float, default=0.5
    )
    args = parser.parse_args()

    if (
        not 0 <= args.dps_weight <= 1
        or not 0 <= args.ehp_weight <= 1
        or abs(args.dps_weight + args.ehp_weight - 1) > 1e-6
    ):
        parser.error("Weights must be 0..1 and sum to 1")
    data = json.loads(SOURCE.read_text(encoding="utf-8"))

    rows = [
        r for r in data["results"]
        if r["status"] == "PASS"
    ]

    if not rows:
        print("No candidates passed constraints.")
        return

    # Sort by DPS, then EHP and resource recovery.
    offensive = sorted(
        rows,
        key=lambda r: (
            -r["stats"]["combinedDPS"],
            -r["stats"]["totalEHP"],
            -r["stats"]["manaRegen"],
            -r["stats"]["manaUnreserved"],
        ),
    )

    # Sort by EHP first, then DPS and recovery.
    defensive = sorted(
        rows,
        key=lambda r: (
            -r["stats"]["totalEHP"],
            -r["stats"]["combinedDPS"],
            -r["stats"]["energyShieldRecharge"],
            -r["stats"]["manaRegen"],
        ),
    )


    # Balanced profile: explicit DPS/EHP weights.
    DPS_WEIGHT = args.dps_weight
    EHP_WEIGHT = args.ehp_weight

    def balanced_score(row):
        changes = row["changes"]

        return (
            DPS_WEIGHT * changes["dps_percent"]
            + EHP_WEIGHT * changes["ehp_percent"]
        )

    balanced = sorted(
        rows,
        key=lambda r: (
            -balanced_score(r),
            -r["stats"]["manaRegen"],
            -r["stats"]["energyShieldRecharge"],
            -r["stats"]["manaUnreserved"],
        ),
    )


    winners = {
        "offensive": offensive[0],
        "defensive": defensive[0],
        "balanced": balanced[0],
    }

    report = {
        "version": "0.1",
        "source": str(SOURCE),
        "passed": len(rows),
        "winners": winners,
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("=== CONSTRAINT-AWARE RANKING ===")
    print("Passed candidates:", len(rows))

    for label, row in winners.items():
        changes = row["changes"]
        print(f"\n=== {label.upper()} ===")
        print(f"Swap: {row['removeId']} -> {row['addId']}")
        print(f"DPS: {changes['dps_percent']:+.4f}%")
        print(f"EHP: {changes['ehp_percent']:+.4f}%")
        print(
            f"ES Recharge: "
            f"{changes['es_recharge_percent']:+.2f}%"
        )
        print(
            f"Mana Regen: "
            f"{changes['mana_regen_percent']:+.2f}%"
        )
        print(f"Free Mana: {changes['free_mana']:.0f}")

    print(f"\nSaved: {OUTPUT}")


if __name__ == "__main__":
    main()
