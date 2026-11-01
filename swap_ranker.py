
# PoE BuildLab — Swap Ranker v0.1

import json
import math
from pathlib import Path

SOURCE = Path("swap_executed.json")
OUTPUT = Path("swap_ranked.json")

RESISTS = (
    "fireResist",
    "coldResist",
    "lightningResist",
    "chaosResist",
)

def numeric(stats, key):
    value = stats.get(key)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"Missing/invalid {key}: {value}")
    return float(value)


def eligible(row, base):
    if row.get("validation", {}).get("status") != "VALID":
        return False

    new = row["stats"]

    if numeric(new, "manaUnreserved") < numeric(new, "manaCost"):
        return False

    for key in RESISTS:
        if numeric(new, key) < numeric(base, key) - 1e-6:
            return False

    return True


def dominates(a, b):
    a_stats = a["stats"]
    b_stats = b["stats"]

    a_dps = numeric(a_stats, "combinedDPS")
    b_dps = numeric(b_stats, "combinedDPS")
    a_ehp = numeric(a_stats, "totalEHP")
    b_ehp = numeric(b_stats, "totalEHP")

    epsilon = 1e-5

    return (
        a_dps >= b_dps - epsilon
        and a_ehp >= b_ehp - epsilon
        and (
            a_dps > b_dps + epsilon
            or a_ehp > b_ehp + epsilon
        )
    )


def main():
    data = json.loads(SOURCE.read_text(encoding="utf-8"))

    if not data.get("complete"):
        raise RuntimeError("Experiment report is incomplete")

    baseline = data["baseline"]["stats"]
    rows = data["results"]

    valid = [r for r in rows if eligible(r, baseline)]

    frontier = [
        row for row in valid
        if not any(
            dominates(other, row)
            for other in valid
            if other is not row
        )
    ]

    def enrich(row):
        new = row["stats"]

        return {
            "removeId": row["removeId"],
            "addId": row["addId"],
            "removeName": row["removeName"],
            "addName": row["addName"],
            "dpsGainPercent": row["dpsGainPercent"],
            "ehpChange": row["ehpChange"],
            "esRechargeChange": (
                numeric(new, "energyShieldRecharge")
                - numeric(baseline, "energyShieldRecharge")
            ),
            "manaRegenChange": (
                numeric(new, "manaRegen")
                - numeric(baseline, "manaRegen")
            ),
            "freeMana": numeric(new, "manaUnreserved"),
        }

    results = [enrich(r) for r in frontier]

    # Presentation order only, not an objective fitness score.
    results.sort(
        key=lambda r: (
            -r["dpsGainPercent"],
            -r["ehpChange"],
            -r["esRechargeChange"],
            -r["manaRegenChange"],
            -r["freeMana"],
        )
    )

    report = {
        "version": "0.1",
        "sourceXmlSha256": data["xmlSha256"],
        "sourceHashesVerified": data["sourceHashesVerified"],
        "planned": data["planned"],
        "calculated": len(rows),
        "eligible": len(valid),
        "paretoCount": len(results),
        "pareto": results,
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("=== AUTOMATED SWAP RANKING ===")
    print("Calculated:", len(rows))
    print("Eligible:", len(valid))
    print("Pareto variants:", len(results))

    print("\n=== PARETO RESULTS ===")
    for r in results:
        print(
            f"{r['removeId']} -> {r['addId']}: "
            f"DPS {r['dpsGainPercent']:+.4f}%, "
            f"EHP {r['ehpChange']:+.2f}, "
            f"ES recharge {r['esRechargeChange']:+.2f}, "
            f"Mana regen {r['manaRegenChange']:+.2f}, "
            f"Free mana {r['freeMana']:.0f}"
        )

    print("\nSaved:", OUTPUT)


if __name__ == "__main__":
    main()
