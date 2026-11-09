
# PoE BuildLab AI — Constraint Interaction Analyzer v1.4
# Read-only diagnostics. No PoB calls.

import os
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from experiment_storage import (
    get_experiment_dir,
    load_report,
)

SKILL_GROUP = 6

FIELDS = (
    "energyShield",
    "energyShieldRecharge",
    "manaUnreserved",
    "manaRegen",
    "manaCost",
)


def changes_from_baseline(stats, baseline):
    changes = {}

    for field in FIELDS:
        base = baseline.get(field)
        current = stats.get(field)

        if base is None or current is None:
            changes[field] = None
            continue

        changes[field] = round(current - base, 5)

    return changes


def main():
    raw = os.environ.get("BUILD_XML")
    if not raw:
        raise RuntimeError("BUILD_XML is not set")

    xml = Path(raw).resolve()
    directory = get_experiment_dir(xml, SKILL_GROUP)

    baseline_report = load_report(
        directory / "swap_executed.json",
        xml, SKILL_GROUP,
    )
    baseline = baseline_report["baseline"]["stats"]

    pool_report = load_report(
        directory / "multi_swap_candidate_pool.json",
        xml, SKILL_GROUP,
    )
    predictions = {
        x["key"]: x for x in pool_report["candidates"]
    }

    executed = load_report(
        directory / "multi_swap_executed_v12.json",
        xml, SKILL_GROUP,
    )

    calculated = executed["results"]
    rejects = [
        x for x in calculated
        if x["status"] == "REJECT"
    ]

    reason_counts = Counter()
    by_removal = defaultdict(list)
    predicted_actual = Counter()

    for row in calculated:
        predicted = predictions.get(row["key"])
        if predicted is None:
            raise RuntimeError(
                f"Missing prediction: {row['key']}"
            )

        predicted_actual[
            (predicted["predictedStatus"], row["status"])
        ] += 1

        removals = row["key"].split("->", 1)[0]
        by_removal[removals].append(row)

        if row["status"] == "REJECT":
            reason_counts.update(row["problems"])

    print("=== CONSTRAINT INTERACTION ANALYZER v1.4 ===")
    print("Calculated:", len(calculated))
    print("PASS:", len(calculated) - len(rejects))
    print("REJECT:", len(rejects))

    print("\nBASELINE:")
    for field in FIELDS:
        print(f"  {field}: {baseline.get(field)}")

    print("\nPREDICTED -> ACTUAL:")
    for predicted in ("PASS", "REJECT"):
        for actual in ("PASS", "REJECT"):
            print(
                f"  {predicted} -> {actual}:",
                predicted_actual[(predicted, actual)],
            )

    print("\nREJECTION REASONS:")
    for reason, count in reason_counts.most_common():
        print(" ", reason, count)

    print("\nREJECTED COMBINATIONS:")
    for row in sorted(
        rejects,
        key=lambda x: -(
            x["changes"]["dps_percent"]
            + x["changes"]["ehp_percent"]
        ),
    ):
        delta = changes_from_baseline(
            row["stats"], baseline
        )
        predicted = predictions[row["key"]]

        print("\n ", row["key"])
        print(
            "  DPS:", round(
                row["changes"]["dps_percent"], 4
            ),
            "EHP:", round(
                row["changes"]["ehp_percent"], 4
            ),
        )
        print("  Problems:", row["problems"])
        print(
            "  Predicted problems:",
            predicted.get("predictedProblems", []),
        )

        for field in FIELDS:
            print(
                f"  {field}: {row['stats'].get(field)}"
                f"  (delta: {delta[field]})"
            )

    print("\nREMOVAL PAIR STATISTICS:")
    for removal, rows in sorted(
        by_removal.items(),
        key=lambda entry: (
            -len(entry[1]),
            entry[0],
        ),
    ):
        if len(rows) < 2:
            continue

        fail = [
            x for x in rows if x["status"] == "REJECT"
        ]

        recharge = [
            x["changes"]["es_recharge_percent"]
            for x in rows
        ]

        print(
            removal,
            "N:", len(rows),
            "REJECT:", len(fail),
            "Mean recharge change:",
            round(mean(recharge), 4),
            "%",
        )

    print("\nDiagnostic only. No model changes.")


if __name__ == "__main__":
    main()
