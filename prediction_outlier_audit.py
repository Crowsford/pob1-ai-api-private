
import os
from statistics import mean
from experiment_storage import get_experiment_dir, load_report

p = os.environ["BUILD_XML"]
d = get_experiment_dir(p, 6)

single = load_report(d / "swap_constrained.json", p, 6)
multi = load_report(d / "multi_swap_results.json", p, 6)
recovery = load_report(d / "recovery_results.json", p, 6)

lookup = {
    (int(x["removeId"]), int(x["addId"])):
        x["changes"]["dps_percent"]
    for x in single["results"]
}

groups = {
    "ALL": [],
    "CONTAINS_BOTH_9392_55571": [],
    "OTHER": [],
}

for row in multi["results"] + recovery["results"]:
    removed, added = row["key"].split("->")
    rs = [int(x) for x in removed.split(",")]
    ads = [int(x) for x in added.split(",")]

    predicted = sum(
        lookup[r, a]
        for r in rs
        for a in ads
    ) / 2

    error = row["changes"]["dps_percent"] - predicted

    groups["ALL"].append(error)

    if 9392 in rs and 55571 in ads:
        groups["CONTAINS_BOTH_9392_55571"].append(error)
    else:
        groups["OTHER"].append(error)

print("=== OUTLIER AUDIT ===")

for name, values in groups.items():
    print("\n", name)
    print("Samples:", len(values))

    if values:
        print("MAE:", round(mean(abs(x) for x in values), 5))
        print("Bias:", round(mean(values), 5))
        print("Max error:", round(max(abs(x) for x in values), 5))
