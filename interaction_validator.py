
# PoE BuildLab AI — Interaction Validator v1.3.2
# Diagnostic only. No PoB calls, no changes to optimizer.

import os
from collections import defaultdict
from pathlib import Path
from statistics import mean

from experiment_storage import get_experiment_dir, load_report

SKILL_GROUP = 6
MIN_TRAIN = 3
MAX_ERROR_RANGE = 0.05
SHRINKAGE = 2.0

METRICS = (
    ("DPS", "predictedDpsPercent", "dps_percent"),
    ("EHP", "predictedEhpPercent", "ehp_percent"),
    ("Mana Regen", "predictedManaRegenPercent",
     "mana_regen_percent"),
)


def addition_pair(key):
    return key.split("->", 1)[1]


def correction(training_errors):
    n = len(training_errors)

    if n < MIN_TRAIN:
        return 0.0

    spread = max(training_errors) - min(training_errors)

    if spread > MAX_ERROR_RANGE:
        return 0.0

    # Shrink estimates toward zero for small samples.
    return mean(training_errors) * n / (n + SHRINKAGE)


def validate(rows, predicted_field, actual_field):
    records = []

    for row, prediction in rows:
        predicted = float(prediction[predicted_field])
        actual = float(row["changes"][actual_field])

        records.append({
            "key": row["key"],
            "pair": addition_pair(row["key"]),
            "error": actual - predicted,
        })

    grouped = defaultdict(list)

    for item in records:
        grouped[item["pair"]].append(item)

    baseline_errors = []
    corrected_errors = []
    corrected_cases = []

    for item in records:
        training = [
            other["error"]
            for other in grouped[item["pair"]]
            if other is not item
        ]

        adjustment = correction(training)
        baseline_errors.append(abs(item["error"]))
        corrected_errors.append(
            abs(item["error"] - adjustment)
        )

        if abs(adjustment) > 1e-10:
            corrected_cases.append({
                "key": item["key"],
                "actualError": item["error"],
                "correction": adjustment,
                "residualError": item["error"] - adjustment,
            })

    baseline_mae = mean(baseline_errors)
    corrected_mae = mean(corrected_errors)

    return {
        "baselineMAE": baseline_mae,
        "correctedMAE": corrected_mae,
        "correctedCases": corrected_cases,
        "groups": grouped,
    }


def main():
    xml = Path(os.environ["BUILD_XML"]).resolve()
    directory = get_experiment_dir(xml, SKILL_GROUP)

    pool = load_report(
        directory / "multi_swap_candidate_pool.json",
        xml, SKILL_GROUP,
    )
    executed = load_report(
        directory / "multi_swap_executed_v12.json",
        xml, SKILL_GROUP,
    )

    predictions = {
        row["key"]: row
        for row in pool["candidates"]
    }

    rows = []

    for row in executed["results"]:
        key = row["key"]

        if key not in predictions:
            raise RuntimeError(
                f"Missing prediction: {key}"
            )

        rows.append((row, predictions[key]))

    print("=== INTERACTION VALIDATION v1.3.2 ===")
    print("Calculated experiments:", len(rows))
    print("Minimum training samples:", MIN_TRAIN)
    print("Maximum error range:", MAX_ERROR_RANGE)
    print("Shrinkage:", SHRINKAGE)

    for label, predicted, actual in METRICS:
        result = validate(rows, predicted, actual)

        old = result["baselineMAE"]
        new = result["correctedMAE"]

        improvement = (
            100 * (old - new) / old
            if old else 0
        )

        print(f"\n--- {label} ---")
        print("Original MAE:", round(old, 6))
        print("Corrected MAE:", round(new, 6))
        print("MAE reduction:", round(improvement, 2), "%")
        print(
            "Corrected test cases:",
            len(result["correctedCases"]),
        )

        for item in result["correctedCases"][:10]:
            print(
                item["key"],
                "Correction:",
                round(item["correction"], 5),
                "Residual:",
                round(item["residualError"], 5),
            )

    print("\nDiagnostic only: no corrections installed.")


if __name__ == "__main__":
    main()
