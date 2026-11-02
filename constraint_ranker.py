
# PoE BuildLab — Constraint-Aware Ranker v0.3

import argparse
import math
import os
from pathlib import Path

from experiment_storage import (
    get_experiment_dir,
    load_report,
    save_report,
    xml_sha256,
)

SKILL_GROUP = 6


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
        not math.isfinite(args.dps_weight)
        or not math.isfinite(args.ehp_weight)
        or not 0 <= args.dps_weight <= 1
        or not 0 <= args.ehp_weight <= 1
        or abs(args.dps_weight + args.ehp_weight - 1) > 1e-6
    ):
        parser.error(
            "Weights must be finite, between 0 and 1, "
            "and sum to 1"
        )

    xml_raw = os.environ.get("BUILD_XML")
    if not xml_raw:
        raise RuntimeError("BUILD_XML is not set")

    xml_path = Path(xml_raw).resolve()
    xml_hash = xml_sha256(xml_path)

    experiment_dir = get_experiment_dir(
        xml_path, SKILL_GROUP
    )

    source = experiment_dir / "swap_constrained.json"

    profile = (
        f"dps{round(args.dps_weight * 100):03d}_"
        f"ehp{round(args.ehp_weight * 100):03d}"
    )

    output = experiment_dir / f"constraint_ranked_{profile}.json"

    data = load_report(source, xml_path, SKILL_GROUP)

    if data.get("sourceHashesVerified") is not True:
        raise RuntimeError("Unverified experiment sources")

    if data.get("total") != len(data["results"]):
        raise RuntimeError("Incomplete constraint results")

    rows = [
        r for r in data["results"]
        if r["status"] == "PASS"
    ]

    if len(rows) != data["passed"]:
        raise RuntimeError("Passed candidate count mismatch")

    if not rows:
        print("No candidates passed constraints.")
        return

    offensive = sorted(
        rows,
        key=lambda r: (
            -r["stats"]["combinedDPS"],
            -r["stats"]["totalEHP"],
            -r["stats"]["manaRegen"],
            -r["stats"]["manaUnreserved"],
        ),
    )

    defensive = sorted(
        rows,
        key=lambda r: (
            -r["stats"]["totalEHP"],
            -r["stats"]["combinedDPS"],
            -r["stats"]["energyShieldRecharge"],
            -r["stats"]["manaRegen"],
        ),
    )

    def balanced_score(row):
        changes = row["changes"]

        return (
            args.dps_weight * changes["dps_percent"]
            + args.ehp_weight * changes["ehp_percent"]
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

    if xml_sha256(xml_path) != xml_hash:
        raise RuntimeError("XML changed during ranking")

    report = {
        "version": "0.3",
        "source": str(source),
        "xmlPath": str(xml_path),
        "xmlSha256": xml_hash,
        "skillGroup": SKILL_GROUP,
        "sourceHashesVerified": True,
        "weights": {
            "dps": args.dps_weight,
            "ehp": args.ehp_weight,
        },
        "passed": len(rows),
        "winners": winners,
    }

    save_report(output, report)

    print("=== CONSTRAINT-AWARE RANKING v0.3 ===")
    print("Profile:", profile)
    print("Passed candidates:", len(rows))

    for label, row in winners.items():
        changes = row["changes"]

        print(f"\n=== {label.upper()} ===")
        print(
            f"Swap: {row['removeId']} -> {row['addId']}"
        )
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
        print(
            f"Free Mana: {changes['free_mana']:.0f}"
        )
        print(
            f"Spell Block change: "
            f"{changes['spellBlockChance_change']:+.1f}"
        )

    print(f"\nSaved: {output}")


if __name__ == "__main__":
    main()
