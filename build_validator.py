
# PoE BuildLab — Build Validator v0.1

ATTRIBUTES = ("str", "dex", "int")


def check_attributes(result):
    validation = result.get("validation")

    if not isinstance(validation, dict):
        return {
            "status": "UNKNOWN",
            "reason": "Attribute validation data unavailable",
            "deficits": {},
        }

    attributes = validation.get("attributes", {})
    requirements = validation.get("requirements", {})

    deficits = {}

    for attr in ATTRIBUTES:
        actual = attributes.get(attr)
        required = requirements.get(attr)

        if (
            not isinstance(actual, (int, float))
            or not isinstance(required, (int, float))
        ):
            return {
                "status": "UNKNOWN",
                "reason": f"Missing attribute data: {attr}",
                "deficits": deficits,
            }

        deficits[attr] = max(0, required - actual)

    return {
        "status": (
            "INVALID"
            if any(value > 0 for value in deficits.values())
            else "VALID"
        ),
        "deficits": deficits,
    }


def compare_attribute_regressions(baseline, modified):
    before = check_attributes(baseline)
    after = check_attributes(modified)

    if "UNKNOWN" in (before["status"], after["status"]):
        return {
            "status": "UNKNOWN",
            "reason": "Incomplete attribute validation",
        }

    changes = {}

    for attr in ATTRIBUTES:
        old_deficit = before["deficits"][attr]
        new_deficit = after["deficits"][attr]

        changes[attr] = {
            "before": old_deficit,
            "after": new_deficit,
            "difference": new_deficit - old_deficit,
        }

    regressions = {
        attr: data
        for attr, data in changes.items()
        if data["difference"] > 0
    }

    return {
        "status": (
            "REGRESSION" if regressions else "NO_REGRESSION"
        ),
        "changes": changes,
        "regressions": regressions,
    }


def validate_experiment(baseline, modified):
    attributes = check_attributes(modified)
    regression = compare_attribute_regressions(
        baseline, modified
    )

    points_used = modified.get("passivePointsUsed")
    level = modified.get("level")
    extra_points = modified.get("extraPoints")

    if (
        type(points_used) is int
        and type(level) is int
        and type(extra_points) is int
        and 67 <= level <= 100
        and extra_points >= 0
    ):
        maximum = level - 1 + 23 + extra_points
        budget = {
            "status": (
                "VALID"
                if 0 <= points_used <= maximum
                else "INVALID"
            ),
            "used": points_used,
            "maximum": maximum,
        }
    else:
        budget = {
            "status": "UNKNOWN",
            "reason": "Cannot verify passive point budget",
        }

    statuses = (
        attributes["status"],
        budget["status"],
    )

    if "INVALID" in statuses:
        status = "INVALID"
    elif "UNKNOWN" in statuses:
        status = "UNKNOWN"
    else:
        status = "VALID"

    return {
        "status": status,
        "scope": "attributes_and_passive_budget_only",
        "attributes": attributes,
        "budget": budget,
        "attributeRegression": regression,
    }
