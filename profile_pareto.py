
# PoE BuildLab AI — Profile Pareto Engine v1.4
# Builds profile-specific Pareto frontiers.
# No PoB calls. No legacy report modifications.

import argparse
import hashlib
import math
from copy import deepcopy

from build_profile import load_build_profile
from profile_experiment_storage import (
    load_profile_report,
    report_path,
    save_profile_report,
)

METRICS = (
    "dps_percent",
    "ehp_percent",
    "mana_regen_percent",
)

EPS = 1e-7


def metric_values(row):
    values = []

    for key in METRICS:
        value = row["changes"][key]

        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
        ):
            raise ValueError(
                f"Invalid Pareto metric {key}: {row['key']}"
            )

        values.append(float(value))

    return tuple(values)


def dominates(left, right):
    return (
        all(a >= b - EPS for a, b in zip(left, right))
        and any(a > b + EPS for a, b in zip(left, right))
    )


def build_frontier(rows):
    passed = [
        row for row in rows
        if row["status"] == "PASS"
    ]

    points = [
        (row, metric_values(row))
        for row in passed
    ]

    frontier = []

    for index, (row, values) in enumerate(points):
        if not any(
            dominates(other_values, values)
            for other_index, (_, other_values)
            in enumerate(points)
            if other_index != index
        ):
            frontier.append(row)

    frontier.sort(
        key=lambda row: (
            -row["changes"]["dps_percent"],
            -row["changes"]["ehp_percent"],
            -row["changes"]["mana_regen_percent"],
            row["key"],
        )
    )

    unique_points = {
        metric_values(row)
        for row in frontier
    }

    return frontier, len(unique_points)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        default="build_profiles/bababan_test.json",
    )
    parser.add_argument(
        "--strict-recharge",
        action="store_true",
    )
    args = parser.parse_args()

    profile = load_build_profile(args.profile)

    if args.strict_recharge:
        profile = deepcopy(profile)
        profile["build"]["name"] += " - Strict Recharge"
        profile["constraints"][
            "max_es_recharge_loss_percent"
        ] = 0.0

    source_path = report_path(
        profile, "evaluated_results.json"
    )

    source_hash = hashlib.sha256(
        source_path.read_bytes()
    ).hexdigest()

    evaluated = load_profile_report(
        profile, "evaluated_results.json"
    )

    rows = evaluated["results"]

    if len(rows) != evaluated["calculated"]:
        raise RuntimeError("Evaluation count mismatch")

    if any(
        row["status"] not in ("PASS", "REJECT")
        for row in rows
    ):
        raise RuntimeError("Unexpected evaluation status")

    if len({row["key"] for row in rows}) != len(rows):
        raise RuntimeError("Duplicate experiment keys")

    frontier, unique_count = build_frontier(rows)

    passed = sum(
        row["status"] == "PASS" for row in rows
    )

    output = save_profile_report(
        profile,
        "pareto_frontier.json",
        {
            "version": "1.4",
            "sourceReport": "evaluated_results.json",
            "sourceReportSha256": source_hash,
            "metrics": list(METRICS),
            "totalCalculated": len(rows),
            "totalPass": passed,
            "frontierCount": len(frontier),
            "uniqueMetricPoints": unique_count,
            "frontier": frontier,
        },
    )

    print("=== PROFILE PARETO ENGINE v1.4 ===")
    print("Profile:", profile["build"]["name"])
    print("Calculated:", len(rows))
    print("PASS:", passed)
    print("Frontier combinations:", len(frontier))
    print("Unique metric points:", unique_count)

    print("\nTOP FRONTIER:")
    for row in frontier[:15]:
        c = row["changes"]
        print(
            row["key"],
            "DPS:", round(c["dps_percent"], 4),
            "EHP:", round(c["ehp_percent"], 4),
            "Mana:", round(c["mana_regen_percent"], 4),
        )

    print("\nSaved:", output)
    print("PoB calls: 0")


if __name__ == "__main__":
    main()
