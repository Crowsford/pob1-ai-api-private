
# PoE BuildLab AI — Universal Constraints v1
# Independent of class, build type and skill group.
# Does not modify legacy evaluation logic.

import math

OPERATORS = {
    "min",
    "max",
    "max_loss_percent",
}

MISSING_POLICIES = {"error", "skip"}
TOLERANCE = 1e-6


def number(value, context):
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
    ):
        raise ValueError(
            f"Invalid numeric value for {context}: {value}"
        )
    return float(value)


def validate_rules(rules):
    if not isinstance(rules, dict):
        raise ValueError("Rules must be a dictionary")

    for metric, rule in rules.items():
        if not isinstance(metric, str) or not metric:
            raise ValueError("Invalid metric name")

        if not isinstance(rule, dict):
            raise ValueError(f"Invalid rule: {metric}")

        if not rule:
            raise ValueError(f"Empty rule: {metric}")

        unknown = set(rule) - OPERATORS - {"missing"}
        if unknown:
            raise ValueError(
                f"Unknown operators for {metric}: {sorted(unknown)}"
            )

        policy = rule.get("missing", "error")
        if policy not in MISSING_POLICIES:
            raise ValueError(
                f"Invalid missing policy: {metric}"
            )

        if not (set(rule) & OPERATORS):
            raise ValueError(
                f"No numeric constraint for {metric}"
            )

        for operator in OPERATORS & set(rule):
            amount = number(
                rule[operator],
                f"{metric}.{operator}",
            )

            if (
                operator == "max_loss_percent"
                and not 0 <= amount <= 100
            ):
                raise ValueError(
                    f"Invalid loss percentage: {metric}"
                )

        if (
            "min" in rule
            and "max" in rule
            and rule["min"] > rule["max"]
        ):
            raise ValueError(
                f"Contradictory bounds: {metric}"
            )


def evaluate_rules(baseline, candidate, rules):
    validate_rules(rules)

    if not isinstance(baseline, dict):
        raise ValueError("Baseline must be a dictionary")

    if not isinstance(candidate, dict):
        raise ValueError("Candidate must be a dictionary")

    problems = []
    details = {}

    for metric, rule in rules.items():
        policy = rule.get("missing", "error")

        if metric not in candidate:
            if policy == "skip":
                details[metric] = {
                    "status": "SKIPPED",
                    "reason": "MISSING_CANDIDATE",
                }
                continue
            raise ValueError(
                f"Missing candidate metric: {metric}"
            )

        after = number(candidate[metric], metric)

        before = None
        if metric in baseline:
            before = number(
                baseline[metric],
                f"baseline.{metric}",
            )

        if "max_loss_percent" in rule and before is None:
            if policy == "skip":
                details[metric] = {
                    "status": "SKIPPED",
                    "reason": "MISSING_BASELINE",
                }
                continue
            raise ValueError(
                f"Missing baseline metric: {metric}"
            )

        failures = []

        if "min" in rule:
            if after < rule["min"] - TOLERANCE:
                failures.append("BELOW_MIN")

        if "max" in rule:
            if after > rule["max"] + TOLERANCE:
                failures.append("ABOVE_MAX")

        if "max_loss_percent" in rule:
            if before < 0:
                raise ValueError(
                    f"Negative baseline for relative loss: {metric}"
                )

            # For zero baseline, preservation means no
            # decrease below zero. No percentage invented.
            if before == 0:
                if after < -TOLERANCE:
                    failures.append("LOSS_FROM_ZERO")
            else:
                threshold = before * (
                    1 - rule["max_loss_percent"] / 100
                )
                if after < threshold - TOLERANCE:
                    failures.append("RELATIVE_LOSS")

        percent = None
        if before is not None and before > 0:
            percent = (
                100.0 * (after - before) / before
            )

        details[metric] = {
            "status": "FAIL" if failures else "PASS",
            "baseline": before,
            "actual": after,
            "absoluteChange": (
                after - before
                if before is not None else None
            ),
            "percentChange": percent,
            "failures": failures,
        }

        for failure in failures:
            problems.append(f"{metric}:{failure}")

    return {
        "status": "PASS" if not problems else "REJECT",
        "problems": problems,
        "details": details,
    }
