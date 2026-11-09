
import os
from statistics import mean
from experiment_storage import get_experiment_dir, load_report

p = os.environ["BUILD_XML"]
d = get_experiment_dir(p, 6)

single = load_report(d / "swap_constrained.json", p, 6)
multi = load_report(d / "multi_swap_results.json", p, 6)
recovery = load_report(d / "recovery_results.json", p, 6)

lookup = {
    (int(r["removeId"]), int(r["addId"])): r["changes"]
    for r in single["results"]
}

rows = multi["results"] + recovery["results"]
errors = {
    name: {"dps": [], "ehp": []}
    for name in ("A", "B", "MEAN")
}

for row in rows:
    removes, adds = row["key"].split("->")
    r1, r2 = map(int, removes.split(","))
    a1, a2 = map(int, adds.split(","))

    a = (lookup[(r1, a1)], lookup[(r2, a2)])
    b = (lookup[(r1, a2)], lookup[(r2, a1)])

    for metric in ("dps", "ehp"):
        field = metric + "_percent"
        actual = row["changes"][field]

        pa = a[0][field] + a[1][field]
        pb = b[0][field] + b[1][field]

        predictions = {
            "A": pa,
            "B": pb,
            "MEAN": (pa + pb) / 2,
        }

        for name, predicted in predictions.items():
            errors[name][metric].append(actual - predicted)

print("=== PAIRING AUDIT ===")
print("Experiments:", len(rows))

for metric in ("dps", "ehp"):
    print("\n", metric.upper())

    for name in ("A", "B", "MEAN"):
        values = errors[name][metric]

        print(
            name,
            "MAE:", round(mean(abs(x) for x in values), 5),
            "Bias:", round(mean(values), 5),
            "MAX:", round(max(abs(x) for x in values), 5),
        )
