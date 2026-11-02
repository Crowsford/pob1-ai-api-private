
# PoE BuildLab — Build Constraints v0.1

import json
import math
from pathlib import Path

SOURCE = Path("swap_executed.json")
OUTPUT = Path("swap_constrained.json")

# Initial conservative profile for BabaBan 99.
LIMITS = {
    "min_dps_change_percent": 0.0,
    "max_ehp_loss_percent": 0.0,
    "max_es_loss_percent": 0.0,
    "max_es_recharge_loss_percent": 5.0,
    "max_mana_regen_loss_percent": 10.0,
    "min_free_mana": 600.0,
    "min_mana_casts": 2.0,
    "allow_resistance_loss": False,
}

RESISTANCES = (
    "fireResist",
    "coldResist",
    "lightningResist",
    "chaosResist",
)

TOLERANCE = 1e-6


def value(stats, key):
    item = stats.get(key)

    if (
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(item)
    ):
        raise ValueError(f"Missing or invalid stat: {key}={item}")

    return float(item)


def percent_change(original, modified):
    if original <= 0:
        raise ValueError(
            "Cannot calculate relative change from zero "
            "or negative baseline"
        )
    return 100.0 * (modified - original) / original


def evaluate_constraints(baseline, row):
    original = baseline["stats"]
    modified = row["stats"]

    problems = []
    changes = {}

    validation = row.get("validation", {})
    if validation.get("status") != "VALID":
        problems.append("ATTRIBUTE_OR_PASSIVE_VALIDATION")

    measurements = (
        ("combinedDPS", "dps"),
        ("totalEHP", "ehp"),
        ("energyShield", "es"),
        ("energyShieldRecharge", "es_recharge"),
        ("manaRegen", "mana_regen"),
    )

    for stat_key, result_key in measurements:
        before = value(original, stat_key)
        after = value(modified, stat_key)

        changes[result_key + "_percent"] = percent_change(
            before, after
        )

    checks = (
        (
            "dps_percent",
            LIMITS["min_dps_change_percent"],
            "DPS_BELOW_LIMIT",
        ),
        (
            "ehp_percent",
            -LIMITS["max_ehp_loss_percent"],
            "EHP_LOSS",
        ),
        (
            "es_percent",
            -LIMITS["max_es_loss_percent"],
            "ENERGY_SHIELD_LOSS",
        ),
        (
            "es_recharge_percent",
            -LIMITS["max_es_recharge_loss_percent"],
            "ES_RECHARGE_LOSS",
        ),
        (
            "mana_regen_percent",
            -LIMITS["max_mana_regen_loss_percent"],
            "MANA_REGEN_LOSS",
        ),
    )

    for metric, minimum, problem_code in checks:
        if changes[metric] < minimum - TOLERANCE:
            problems.append(problem_code)

    free_mana = value(modified, "manaUnreserved")
    mana_cost = value(modified, "manaCost")

    changes["free_mana"] = free_mana
    changes["mana_cost"] = mana_cost

    if free_mana < LIMITS["min_free_mana"] - TOLERANCE:
        problems.append("LOW_FREE_MANA")

    if (
        free_mana + TOLERANCE
        < mana_cost * LIMITS["min_mana_casts"]
    ):
        problems.append("INSUFFICIENT_MANA_FOR_CASTS")

    for key in RESISTANCES:
        before = value(original, key)
        after = value(modified, key)

        changes[key + "_change"] = after - before

        if not LIMITS["allow_resistance_loss"]:
            if after < before - TOLERANCE:
                problems.append("RESISTANCE_LOSS_" + key)

    return {
        "removeId": row["removeId"],
        "addId": row["addId"],
        "removeName": row["removeName"],
        "addName": row["addName"],
        "status": "PASS" if not problems else "REJECT",
        "problems": problems,
        "changes": changes,
        "stats": modified,
    }


def main():
    data = json.loads(SOURCE.read_text(encoding="utf-8"))

    if data.get("complete") is not True:
        raise RuntimeError("Experiment results are incomplete")

    if len(data["results"]) != data["planned"]:
        raise RuntimeError("Not all planned experiments succeeded")

    results = [
        evaluate_constraints(data["baseline"], row)
        for row in data["results"]
    ]

    passed = [r for r in results if r["status"] == "PASS"]
    rejected = [r for r in results if r["status"] == "REJECT"]

    report = {
        "version": "0.1",
        "source": str(SOURCE),
        "xmlSha256": data.get("xmlSha256"),
        "sourceHashesVerified": data.get(
            "sourceHashesVerified", False
        ),
        "limits": LIMITS,
        "total": len(results),
        "passed": len(passed),
        "rejected": len(rejected),
        "results": results,
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("=== BUILD CONSTRAINTS v0.1 ===")
    print("Total:", len(results))
    print("Passed:", len(passed))
    print("Rejected:", len(rejected))

    print("\n=== TOP 10 PASSED BY DPS ===")

    passed.sort(
        key=lambda r: r["stats"]["combinedDPS"],
        reverse=True,
    )

    for row in passed[:10]:
        c = row["changes"]
        print(
            f"{row['removeId']} -> {row['addId']}: "
            f"DPS {c['dps_percent']:+.4f}%, "
            f"EHP {c['ehp_percent']:+.4f}%, "
            f"ES Recharge {c['es_recharge_percent']:+.2f}%, "
            f"Mana Regen {c['mana_regen_percent']:+.2f}%, "
            f"Free Mana {c['free_mana']:.0f}"
        )

    print("\n=== REJECTION REASONS ===")

    counts = {}
    for row in rejected:
        for reason in row["problems"]:
            counts[reason] = counts.get(reason, 0) + 1

    for reason, count in sorted(
        counts.items(), key=lambda item: (-item[1], item[0])
    ):
        print(f"{reason}: {count}")

    print("\nSaved:", OUTPUT)


if __name__ == "__main__":
    main()
