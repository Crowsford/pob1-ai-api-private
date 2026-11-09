
# PoE BuildLab AI — Build Specification v2
# Validates user requirements BEFORE build generation.
# No PoB or LLM calls.

import json
from pathlib import Path

from universal_constraints import validate_rules

VERSION = 2

DEFENSE_TYPES = {
    "life", "energy_shield", "hybrid", "ward",
    "mana", "auto",
}

BUDGET_UNITS = {"chaos", "divine"}

GOAL_METRICS = {
    "combinedDPS", "totalEHP", "life",
    "energyShield", "energyShieldRecharge",
    "manaRegen", "manaUnreserved",
}

ALLOWED_KEYS = {
    "specVersion", "name", "game", "league",
    "character", "playstyle", "budget",
    "requirements", "objectives", "progression",
}

REQUIRED_KEYS = ALLOWED_KEYS - {"name"}


def require_object(obj, context):
    if not isinstance(obj, dict):
        raise ValueError(f"{context} must be an object")
    return obj


def exact_keys(obj, allowed, required, context):
    unknown = set(obj) - set(allowed)
    missing = set(required) - set(obj)

    if unknown or missing:
        raise ValueError(
            f"{context}: unknown={sorted(unknown)}, "
            f"missing={sorted(missing)}"
        )


def nonempty(value, context):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Invalid string: {context}")
    return value


def positive_int(value, context):
    if type(value) is not int or value < 1:
        raise ValueError(f"Invalid positive integer: {context}")
    return value


def validate_spec(spec):
    require_object(spec, "Specification")
    exact_keys(
        spec, ALLOWED_KEYS, REQUIRED_KEYS, "Specification"
    )

    if spec["specVersion"] != VERSION:
        raise ValueError("Unsupported specification version")

    if spec["game"] != "poe1":
        raise ValueError("Only PoE1 is currently supported")

    if "name" in spec:
        nonempty(spec["name"], "name")

    nonempty(spec["league"], "league")

    character = require_object(
        spec["character"], "character"
    )
    exact_keys(
        character,
        {"class", "ascendancy", "defenseType"},
        {"class", "ascendancy", "defenseType"},
        "character",
    )

    for field in ("class", "ascendancy"):
        nonempty(character[field], f"character.{field}")

    if character["defenseType"] not in DEFENSE_TYPES:
        raise ValueError("Unsupported defense type")

    playstyle = require_object(
        spec["playstyle"], "playstyle"
    )
    exact_keys(
        playstyle,
        {"mainSkill", "avoidMechanics", "preferences"},
        {"mainSkill", "avoidMechanics", "preferences"},
        "playstyle",
    )

    nonempty(playstyle["mainSkill"], "mainSkill")

    for field in ("avoidMechanics", "preferences"):
        values = playstyle[field]
        if not isinstance(values, list):
            raise ValueError(f"{field} must be a list")
        for item in values:
            nonempty(item, field)

    budget = require_object(spec["budget"], "budget")
    exact_keys(
        budget,
        {"unit", "maximum", "stage"},
        {"unit", "maximum", "stage"},
        "budget",
    )

    if budget["unit"] not in BUDGET_UNITS:
        raise ValueError("Unsupported budget unit")

    maximum = budget["maximum"]
    if type(maximum) not in (int, float) or not (
        0 <= maximum < float("inf")
    ):
        raise ValueError("Invalid maximum budget")

    if budget["stage"] not in {
        "league_start", "early_maps", "endgame"
    }:
        raise ValueError("Unsupported budget stage")

    validate_rules(spec["requirements"])

    objectives = require_object(
        spec["objectives"], "objectives"
    )
    exact_keys(
        objectives,
        {"maximize"},
        {"maximize"},
        "objectives",
    )

    maximize = objectives["maximize"]

    if (
        not isinstance(maximize, list)
        or not maximize
        or len(maximize) != len(set(maximize))
        or any(x not in GOAL_METRICS for x in maximize)
    ):
        raise ValueError("Invalid optimization objectives")

    progression = require_object(
        spec["progression"], "progression"
    )
    exact_keys(
        progression,
        {"act1To10", "earlyMaps", "endgame"},
        {"act1To10", "earlyMaps", "endgame"},
        "progression",
    )

    for stage, enabled in progression.items():
        if type(enabled) is not bool:
            raise ValueError(
                f"Progression stage must be boolean: {stage}"
            )

    if not any(progression.values()):
        raise ValueError(
            "At least one progression stage is required"
        )

    return spec


def load_spec(path):
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return validate_spec(data)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    args = parser.parse_args()

    spec = load_spec(args.path)

    print("=== BUILD SPECIFICATION v2 ===")
    print("Result: VALID")
    print("Name:", spec.get("name", "(unnamed)"))
    print("Game:", spec["game"])
    print("League:", spec["league"])
    print("Class:", spec["character"]["class"])
    print("Main skill:", spec["playstyle"]["mainSkill"])
    print("Defense:", spec["character"]["defenseType"])
    print("Requirements:", len(spec["requirements"]))
    print("Objectives:", spec["objectives"]["maximize"])
    print("PoB calls: 0")
    print("LLM calls: 0")
