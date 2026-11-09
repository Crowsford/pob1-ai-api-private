
# PoE BuildLab AI — Prediction Audit v0.1
# Reads saved experiments. Does not run PoB or modify reports.

import os
from statistics import mean

from experiment_storage import get_experiment_dir, load_report

SKILL_GROUP = 6


def main():
    xml_path = os.environ["BUILD_XML"]
    directory = get_experiment_dir(xml_path, SKILL_GROUP)

    singles = load_report(
        directory / "swap_constrained.json",
        xml_path, SKILL_GROUP,
    )
    doubles = load_report(
        directory / "multi_swap_results.json",
        xml_path, SKILL_GROUP,
    )
    recovery = load_report(
        directory / "recovery_results.json",
        xml_path, SKILL_GROUP,
    )

    single_lookup = {}

    for row in singles["results"]:
        key = (int(row["removeId"]), int(row["addId"]))

        if key in single_lookup:
            raise RuntimeError(f"Duplicate single swap: {key}")

        single_lookup[key] = row["changes"]

    all_rows = [
        ("MULTI", row) for row in doubles["results"]
    ] + [
        ("RECOVERY", row) for row in recovery["results"]
    ]

    seen = set()
    audited = []
    missing = []

    for source, row in all_rows:
        key = row["key"]

        if key in seen:
            raise RuntimeError(f"Duplicate double swap: {key}")

        seen.add(key)

        removals, additions = key.split("->")
        r1, r2 = map(int, removals.split(","))
        a1, a2 = map(int, additions.split(","))

        # Two possible pairings of the same four nodes.
        pairings = [
            ((r1, a1), (r2, a2)),
            ((r1, a2), (r2, a1)),
        ]

        estimates = []

        for first, second in pairings:
            if first not in single_lookup or second not in single_lookup:
                continue

            x = single_lookup[first]
            y = single_lookup[second]

            estimates.append({
                "dps": x["dps_percent"] + y["dps_percent"],
                "ehp": x["ehp_percent"] + y["ehp_percent"],
            })

        if not estimates:
            missing.append(key)
            continue

        actual = row["changes"]

        predicted_dps = mean(x["dps"] for x in estimates)
        predicted_ehp = mean(x["ehp"] for x in estimates)

        actual_dps = actual["dps_percent"]
        actual_ehp = actual["ehp_percent"]

        audited.append({
            "key": key,
            "source": source,
            "status": row["status"],
            "predDps": predicted_dps,
            "predEhp": predicted_ehp,
            "actualDps": actual_dps,
            "actualEhp": actual_ehp,
            "dpsError": actual_dps - predicted_dps,
            "ehpError": actual_ehp - predicted_ehp,
            "dpsSpread": max(x["dps"] for x in estimates)
                         - min(x["dps"] for x in estimates),
            "ehpSpread": max(x["ehp"] for x in estimates)
                         - min(x["ehp"] for x in estimates),
        })

    if not audited:
        raise RuntimeError("No experiments to audit")

    print("=== PREDICTION AUDIT v0.1 ===")
    print("Single swaps:", len(single_lookup))
    print("Double calculations:", len(all_rows))
    print("Audited:", len(audited))
    print("Missing predictions:", len(missing))

    for metric in ("dps", "ehp"):
        errors = [r[metric + "Error"] for r in audited]
        spreads = [r[metric + "Spread"] for r in audited]

        print(f"\n=== {metric.upper()} ACCURACY ===")
        print(f"Mean error: {mean(errors):+.4f} pp")
        print(f"Mean absolute error: {mean(abs(x) for x in errors):.4f} pp")
        print(f"Maximum absolute error: {max(abs(x) for x in errors):.4f} pp")
        print(f"Maximum pairing spread: {max(spreads):.4f} pp")

        print("\nLargest prediction errors:")
        for row in sorted(
            audited,
            key=lambda r: abs(r[metric + "Error"]),
            reverse=True,
        )[:5]:
            print(
                row["key"],
                f"predicted={row['pred' + metric.capitalize()]:+.4f}%",
                f"actual={row['actual' + metric.capitalize()]:+.4f}%",
                f"error={row[metric + 'Error']:+.4f} pp",
            )

    print("\n=== POSITIVE DPS INTERACTIONS ===")
    for row in sorted(
        audited,
        key=lambda r: r["dpsError"],
        reverse=True,
    )[:5]:
        print(
            row["key"],
            f"DPS interaction={row['dpsError']:+.4f} pp",
            f"EHP interaction={row['ehpError']:+.4f} pp",
            f"status={row['status']}",
        )

    print("\n=== POSITIVE EHP INTERACTIONS ===")
    for row in sorted(
        audited,
        key=lambda r: r["ehpError"],
        reverse=True,
    )[:5]:
        print(
            row["key"],
            f"EHP interaction={row['ehpError']:+.4f} pp",
            f"DPS interaction={row['dpsError']:+.4f} pp",
            f"status={row['status']}",
        )

    if missing:
        print("\nMissing keys:", missing[:10])


if __name__ == "__main__":
    main()
