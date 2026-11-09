
# PoE BuildLab — Build Constraints v0.2

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
TOLERANCE = 1e-6

LIMITS = {
    "min_dps_change_percent": 0.0,
    "max_ehp_loss_percent": 0.0,
    "max_es_loss_percent": 0.0,
    "max_es_recharge_loss_percent": 5.0,
    "max_mana_regen_loss_percent": 10.0,
    "min_free_mana": 500.0,
    "max_free_mana_loss_percent": 10.0,
    "min_mana_casts": 2.0,
    "allow_resistance_loss": False,
    "allow_block_loss": False,
    "allow_suppression_loss": False,
}

RESISTANCES = (
    "fireResist",
    "coldResist",
    "lightningResist",
    "chaosResist",
)

BLOCK_STATS = (
    "blockChance",
    "spellBlockChance",
    "blockChanceMax",
    "spellBlockChanceMax",
)

SUPPRESSION_STATS = (
    "spellSuppressionChance",
    "effectiveSpellSuppressionChance",
    "spellSuppressionEffect",
)


def value(stats, key):
    item = stats.get(key)

    if (
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(item)
    ):
        raise ValueError(
            f"Missing or invalid stat: {key}={item}"
        )

    return float(item)


def percent_change(original, modified):
    # Retain exact legacy behavior for positive baselines.
    if original > 0:
        return 100.0 * (modified - original) / original

    if original < 0:
        raise ValueError(
            "Negative baseline requires an explicit metric policy"
        )

    if modified < 0:
        raise ValueError(
            "Negative result from zero baseline is invalid"
        )

    # Zero -> zero is unchanged.
    if modified == 0:
        return 0.0

    # Zero -> positive: relative change is undefined.
    # The absolute change is tracked separately.
    return None


def evaluate_constraints(baseline, row, limits=None):
    # Preserve old two-argument behavior.
    if limits is None:
        limits = LIMITS

    if not isinstance(limits, dict):
        raise ValueError("Constraints must be a dictionary")

    if set(limits) != set(LIMITS):
        raise ValueError("Incomplete or unknown constraints")

    for key, default in LIMITS.items():
        item = limits[key]
        if isinstance(default, bool):
            valid = type(item) is bool
        else:
            valid = (
                type(item) in (int, float)
                and math.isfinite(item)
                and item >= 0
            )
        if not valid:
            raise ValueError(f"Invalid constraint value: {key}")

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

        changes[result_key + "_percent"] = (
            percent_change(before, after)
        )

        if before == 0:
            changes[result_key + "_absolute_change"] = (
                after - before
            )

    checks = (
        (
            "dps_percent",
            limits["min_dps_change_percent"],
            "DPS_BELOW_LIMIT",
        ),
        (
            "ehp_percent",
            -limits["max_ehp_loss_percent"],
            "EHP_LOSS",
        ),
        (
            "es_percent",
            -limits["max_es_loss_percent"],
            "ENERGY_SHIELD_LOSS",
        ),
        (
            "es_recharge_percent",
            -limits["max_es_recharge_loss_percent"],
            "ES_RECHARGE_LOSS",
        ),
        (
            "mana_regen_percent",
            -limits["max_mana_regen_loss_percent"],
            "MANA_REGEN_LOSS",
        ),
    )

    for metric, minimum, problem_code in checks:
        change = changes[metric]

        if change is None:
            # Relative improvement cannot be evaluated
            # from a zero baseline. Never invent a percent.
            if (
                metric == "dps_percent"
                and minimum > TOLERANCE
            ):
                problems.append("DPS_PERCENT_UNDEFINED")
            continue

        if change < minimum - TOLERANCE:
            problems.append(problem_code)

    # Mana constraints
    baseline_free_mana = value(
        original, "manaUnreserved"
    )
    free_mana = value(modified, "manaUnreserved")
    mana_cost = value(modified, "manaCost")

    changes["free_mana"] = free_mana
    changes["mana_cost"] = mana_cost
    changes["free_mana_percent"] = percent_change(
        baseline_free_mana, free_mana
    )

    if free_mana < limits["min_free_mana"] - TOLERANCE:
        problems.append("LOW_FREE_MANA")

    if baseline_free_mana == 0:
        changes["free_mana_absolute_change"] = (
            free_mana - baseline_free_mana
        )

    if (
        changes["free_mana_percent"] is not None
        and changes["free_mana_percent"]
        < -limits["max_free_mana_loss_percent"]
        - TOLERANCE
    ):
        problems.append("FREE_MANA_LOSS")

    if (
        free_mana + TOLERANCE
        < mana_cost * limits["min_mana_casts"]
    ):
        problems.append("INSUFFICIENT_MANA_FOR_CASTS")

    # Resistances
    for key in RESISTANCES:
        before = value(original, key)
        after = value(modified, key)

        changes[key + "_change"] = after - before

        if not limits["allow_resistance_loss"]:
            if after < before - TOLERANCE:
                problems.append("RESISTANCE_LOSS_" + key)

    # Attack/spell block and block caps
    for key in BLOCK_STATS:
        before = value(original, key)
        after = value(modified, key)

        changes[key + "_change"] = after - before

        if not limits["allow_block_loss"]:
            if after < before - TOLERANCE:
                problems.append("BLOCK_LOSS_" + key)

    # Spell suppression
    for key in SUPPRESSION_STATS:
        before = value(original, key)
        after = value(modified, key)

        changes[key + "_change"] = after - before

        if not limits["allow_suppression_loss"]:
            if after < before - TOLERANCE:
                problems.append("SUPPRESSION_LOSS_" + key)

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
    xml_raw = os.environ.get("BUILD_XML")
    if not xml_raw:
        raise RuntimeError("BUILD_XML is not set")

    xml_path = Path(xml_raw).resolve()
    xml_hash = xml_sha256(xml_path)

    experiment_dir = get_experiment_dir(
        xml_path, SKILL_GROUP
    )

    source = experiment_dir / "swap_executed.json"
    output = experiment_dir / "swap_constrained.json"

    data = load_report(source, xml_path, SKILL_GROUP)

    if data.get("sourceHashesVerified") is not True:
        raise RuntimeError("Unverified experiment sources")

    if data.get("complete") is not True:
        raise RuntimeError("Experiment results are incomplete")

    if data.get("rejected"):
        raise RuntimeError("Swap execution contains rejected runs")

    if len(data["results"]) != data["planned"]:
        raise RuntimeError("Not all planned experiments succeeded")

    results = [
        evaluate_constraints(data["baseline"], row)
        for row in data["results"]
    ]

    passed = [
        r for r in results if r["status"] == "PASS"
    ]
    rejected = [
        r for r in results if r["status"] == "REJECT"
    ]

    if xml_sha256(xml_path) != xml_hash:
        raise RuntimeError("XML changed during constraint evaluation")

    report = {
        "version": "0.2",
        "source": str(source),
        "xmlPath": str(xml_path),
        "xmlSha256": xml_hash,
        "skillGroup": SKILL_GROUP,
        "sourceHashesVerified": True,
        "limits": LIMITS,
        "total": len(results),
        "passed": len(passed),
        "rejected": len(rejected),
        "results": results,
    }

    save_report(output, report)

    print("=== BUILD CONSTRAINTS v0.2 ===")
    print("Total:", len(results))
    print("Passed:", len(passed))
    print("Rejected:", len(rejected))

    passed.sort(
        key=lambda r: r["stats"]["combinedDPS"],
        reverse=True,
    )

    print("\n=== TOP 10 PASSED BY DPS ===")

    for row in passed[:10]:
        c = row["changes"]

        print(
            f"{row['removeId']} -> {row['addId']}: "
            f"DPS {c['dps_percent']:+.4f}%, "
            f"EHP {c['ehp_percent']:+.4f}%, "
            f"ES Recharge {c['es_recharge_percent']:+.2f}%, "
            f"Mana Regen {c['mana_regen_percent']:+.2f}%, "
            f"Free Mana {c['free_mana']:.0f}, "
            f"Spell Block {c['spellBlockChance_change']:+.1f}"
        )

    print("\n=== REJECTION REASONS ===")

    counts = {}
    for row in rejected:
        for reason in row["problems"]:
            counts[reason] = counts.get(reason, 0) + 1

    for reason, count in sorted(
        counts.items(),
        key=lambda item: (-item[1], item[0])
    ):
        print(f"{reason}: {count}")

    print("\nSaved:", output)


if __name__ == "__main__":
    raise SystemExit(
        "Use this module through evaluate_constraints(); "
        "the legacy report writer is disabled."
    )
