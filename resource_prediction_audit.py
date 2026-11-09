
# PoE BuildLab AI — Resource Prediction Audit v0.1
# Read-only analysis of existing experiments.

import os
from statistics import mean

from experiment_storage import get_experiment_dir, load_report

p = os.environ["BUILD_XML"]
d = get_experiment_dir(p, 6)

single = load_report(d / "swap_constrained.json", p, 6)
multi = load_report(d / "multi_swap_results.json", p, 6)
recovery = load_report(d / "recovery_results.json", p, 6)
adaptive = load_report(d / "adaptive_results.json", p, 6)

lookup = {
    (int(x["removeId"]), int(x["addId"])): x["changes"]
    for x in single["results"]
}

rows = (
    multi["results"]
    + recovery["results"]
    + adaptive["results"]
)

metrics = [
    "free_mana_percent",
    "es_recharge_percent",
    "mana_regen_percent",
    "dps_percent",
    "ehp_percent",
]

print("=== RESOURCE PREDICTION AUDIT ===")
print("Experiments:", len(rows))

for metric in metrics:
    errors = []
    threshold_crossings = 0

    for row in rows:
        removed, added = row["key"].split("->")

        rs = [int(x) for x in removed.split(",")]
        ads = [int(x) for x in added.split(",")]

        predicted = sum(
            lookup[r, a][metric]
            for r in rs
            for a in ads
        ) / 2

        actual = row["changes"][metric]
        errors.append(actual - predicted)

        if metric == "free_mana_percent":
            if predicted >= -10 and actual < -10:
                threshold_crossings += 1

        elif metric == "es_recharge_percent":
            if predicted >= -5 and actual < -5:
                threshold_crossings += 1

        elif metric == "mana_regen_percent":
            if predicted >= -10 and actual < -10:
                threshold_crossings += 1

        elif metric in ("dps_percent", "ehp_percent"):
            if predicted >= 0 and actual < 0:
                threshold_crossings += 1

    print("\n", metric)
    print("MAE:", round(mean(abs(x) for x in errors), 5), "pp")
    print("Bias:", round(mean(errors), 5), "pp")
    print("Maximum error:", round(max(abs(x) for x in errors), 5), "pp")
    print("False threshold passes:", threshold_crossings)
