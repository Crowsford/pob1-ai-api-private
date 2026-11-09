
# PoE BuildLab AI — Prediction Calibration v1.3
# Diagnostic only. Does not run PoB or modify build data.

import math
import os
from collections import Counter
from pathlib import Path
from statistics import mean, median

from experiment_storage import (
    get_experiment_dir,
    load_report,
    save_report,
    xml_sha256,
)

SKILL_GROUP = 6

METRICS = {
    "DPS": (
        "predictedDpsPercent",
        "dps_percent",
    ),
    "EHP": (
        "predictedEhpPercent",
        "ehp_percent",
    ),
    "Mana Regen": (
        "predictedManaRegenPercent",
        "mana_regen_percent",
    ),
}


def metric_summary(rows, predicted_field, actual_field):
    errors = []

    for predicted, actual in rows:
        p = float(predicted[predicted_field])
        a = float(actual["changes"][actual_field])

        if not math.isfinite(p) or not math.isfinite(a):
            raise RuntimeError("Non-finite metric")

        errors.append(a - p)

    if not errors:
        return None

    absolute = [abs(e) for e in errors]

    return {
        "count": len(errors),
        "MAE": mean(absolute),
        "medianAbsoluteError": median(absolute),
        "bias": mean(errors),
        "maxAbsoluteError": max(absolute),
    }


def main():
    raw = os.environ.get("BUILD_XML")
    if not raw:
        raise RuntimeError("BUILD_XML is not set")

    xml = Path(raw).resolve()
    digest = xml_sha256(xml)
    directory = get_experiment_dir(xml, SKILL_GROUP)

    pool = load_report(
        directory / "multi_swap_candidate_pool.json",
        xml, SKILL_GROUP,
    )

    actual = load_report(
        directory / "multi_swap_executed_v12.json",
        xml, SKILL_GROUP,
    )

    if pool.get("version") != "1.2-pool":
        raise RuntimeError("Unexpected pool version")

    if actual.get("version") != "1.2":
        raise RuntimeError("Unexpected execution version")

    predictions = {}

    for candidate in pool["candidates"]:
        key = candidate["key"]
        if key in predictions:
            raise RuntimeError(f"Duplicate prediction: {key}")
        predictions[key] = candidate

    calculated = actual["results"]

    pairs = []
    missing = []
    confusion = Counter()
    problems = Counter()

    for row in calculated:
        key = row["key"]
        predicted = predictions.get(key)

        if predicted is None:
            missing.append(key)
            continue

        predicted_status = predicted["predictedStatus"]
        actual_status = row["status"]

        if predicted_status not in ("PASS", "REJECT"):
            raise RuntimeError(
                f"Invalid predicted status for {key}"
            )

        if actual_status not in ("PASS", "REJECT"):
            raise RuntimeError(
                f"Invalid actual status for {key}"
            )

        confusion[(predicted_status, actual_status)] += 1
        problems.update(row.get("problems", []))
        pairs.append((predicted, row))

    if missing:
        raise RuntimeError(
            f"Missing predictions for {len(missing)} keys: "
            f"{missing[:5]}"
        )

    metric_results = {}

    for name, (pred_field, actual_field) in METRICS.items():
        metric_results[name] = metric_summary(
            pairs, pred_field, actual_field
        )

    # Investigate the largest errors in the combined
    # DPS + EHP prediction.
    outliers = []

    for predicted, row in pairs:
        changes = row["changes"]

        dps_error = (
            changes["dps_percent"]
            - predicted["predictedDpsPercent"]
        )

        ehp_error = (
            changes["ehp_percent"]
            - predicted["predictedEhpPercent"]
        )

        outliers.append({
            "key": row["key"],
            "actualStatus": row["status"],
            "predictedStatus": predicted["predictedStatus"],
            "dpsError": dps_error,
            "ehpError": ehp_error,
            "combinedAbsoluteError": (
                abs(dps_error) + abs(ehp_error)
            ),
            "problems": row.get("problems", []),
        })

    outliers.sort(
        key=lambda r: -r["combinedAbsoluteError"]
    )

    predicted_pass = sum(
        count
        for (pred, observed), count in confusion.items()
        if pred == "PASS"
    )

    true_pass = confusion[("PASS", "PASS")]

    precision = (
        true_pass / predicted_pass
        if predicted_pass else None
    )

    report = {
        "version": "1.3-diagnostic",
        "xmlPath": str(xml),
        "xmlSha256": digest,
        "skillGroup": SKILL_GROUP,
        "calculated": len(calculated),
        "matched": len(pairs),
        "invalidTrees": len(actual["invalidTrees"]),
        "invalidCandidates": len(actual["invalidCandidates"]),
        "metricErrors": metric_results,
        "confusion": {
            f"{pred}->{observed}": count
            for (pred, observed), count in confusion.items()
        },
        "predictedPassPrecision": precision,
        "rejectionReasons": dict(problems),
        "worstPredictions": outliers[:20],
    }

    if xml_sha256(xml) != digest:
        raise RuntimeError("Source XML changed")

    output = directory / "prediction_calibration_v13.json"
    save_report(output, report)

    print("=== PREDICTION CALIBRATION v1.3 ===")
    print("Calculated:", len(calculated))
    print("Matched:", len(pairs))
    print("Invalid trees:", report["invalidTrees"])
    print("Invalid candidates:", report["invalidCandidates"])

    print("\nMETRIC ERRORS (percentage points)")
    for name, summary in metric_results.items():
        print(
            name,
            "MAE:", round(summary["MAE"], 5),
            "Bias:", round(summary["bias"], 5),
            "Max:", round(summary["maxAbsoluteError"], 5),
        )

    print("\nPREDICTED -> ACTUAL")
    for prediction in ("PASS", "REJECT"):
        for observed in ("PASS", "REJECT"):
            print(
                f"{prediction} -> {observed}:",
                confusion[(prediction, observed)],
            )

    print(
        "Predicted PASS precision:",
        round(precision * 100, 2)
        if precision is not None else "N/A",
        "%",
    )

    print("\nREJECTION REASONS")
    for reason, count in problems.most_common():
        print(reason, count)

    print("\nWORST PREDICTIONS")
    for row in outliers[:10]:
        print(
            row["key"],
            "DPS error:", round(row["dpsError"], 4),
            "EHP error:", round(row["ehpError"], 4),
            "Status:", row["actualStatus"],
        )

    print("\nSaved:", output)


if __name__ == "__main__":
    main()
