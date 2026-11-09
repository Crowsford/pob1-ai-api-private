
import itertools
import os
from collections import Counter

from experiment_storage import get_experiment_dir, load_report

p = os.environ["BUILD_XML"]
d = get_experiment_dir(p, 6)

single = load_report(d / "swap_constrained.json", p, 6)
multi = load_report(d / "multi_swap_results.json", p, 6)
recovery = load_report(d / "recovery_results.json", p, 6)
adaptive = load_report(d / "adaptive_results.json", p, 6)

matrix = {
    (int(x["removeId"]), int(x["addId"])): x["changes"]
    for x in single["results"]
}

removals = sorted({r for r, _ in matrix})
additions = sorted({a for _, a in matrix})

checked = set()

for report in (multi, recovery, adaptive):
    checked.update(x["key"] for x in report["candidates"])

counts = Counter()
eligible = []

for rs in itertools.combinations(removals, 2):
    for ads in itertools.combinations(additions, 2):
        if set(rs) & set(ads):
            continue

        key = (
            ",".join(map(str, rs))
            + "->"
            + ",".join(map(str, ads))
        )

        if key in checked:
            continue

        def estimate(field):
            return sum(
                matrix[r, a][field]
                for r in rs for a in ads
            ) / 2

        dps = estimate("dps_percent")
        ehp = estimate("ehp_percent")
        mana = estimate("free_mana_percent")
        recharge = estimate("es_recharge_percent")
        regen = estimate("mana_regen_percent")

        if 9392 in rs and 55571 in ads:
            dps -= 0.33516

        counts["unexplored"] += 1

        if mana < -10:
            counts["mana_fail"] += 1
        if recharge < -5:
            counts["recharge_fail"] += 1
        if regen < -10:
            counts["regen_fail"] += 1
        if dps < 0:
            counts["dps_fail"] += 1

        if (
            dps >= 0.03
            and ehp >= 0
            and mana >= -10
            and recharge >= -5
            and regen >= -10
        ):
            eligible.append((key, dps, ehp))
            counts["eligible"] += 1

print("=== CANDIDATE POOL AUDIT ===")
print("Unexplored:", counts["unexplored"])
print("Predicted eligible:", counts["eligible"])
print("Predicted mana failures:", counts["mana_fail"])
print("Predicted recharge failures:", counts["recharge_fail"])
print("Predicted regen failures:", counts["regen_fail"])
print("Predicted DPS failures:", counts["dps_fail"])

print("\nTOP 10 PREDICTED ELIGIBLE:")
for key, dps, ehp in sorted(
    eligible,
    key=lambda x: (x[1] + x[2]),
    reverse=True,
)[:10]:
    print(key, f"DPS {dps:+.4f}%", f"EHP {ehp:+.4f}%")
