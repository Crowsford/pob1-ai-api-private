
# PoE BuildLab AI — Factorized Predictor v0.1
# Analysis only: no PoB calculations, no report changes.

import os
from collections import defaultdict
from statistics import mean

from experiment_storage import get_experiment_dir, load_report


def main():
    xml_path = os.environ["BUILD_XML"]
    directory = get_experiment_dir(xml_path, 6)

    singles = load_report(
        directory / "swap_constrained.json", xml_path, 6
    )
    doubles = load_report(
        directory / "multi_swap_results.json", xml_path, 6
    )
    recovery = load_report(
        directory / "recovery_results.json", xml_path, 6
    )

    fields = ("dps_percent", "ehp_percent")
    rows = singles["results"]

    removals = sorted({int(r["removeId"]) for r in rows})
    additions = sorted({int(r["addId"]) for r in rows})

    matrix = {
        (int(r["removeId"]), int(r["addId"])): r["changes"]
        for r in rows
    }

    assert len(matrix) == len(removals) * len(additions)

    print("=== FACTORIZED PREDICTOR v0.1 ===")
    print("Matrix:", len(removals), "x", len(additions))

    for field in fields:
        global_mean = mean(
            matrix[r, a][field]
            for r in removals
            for a in additions
        )

        remove_effect = {
            r: mean(matrix[r, a][field] for a in additions)
               - global_mean
            for r in removals
        }

        add_effect = {
            a: mean(matrix[r, a][field] for r in removals)
               - global_mean
            for a in additions
        }

        residuals = {
            (r, a): (
                matrix[r, a][field]
                - global_mean
                - remove_effect[r]
                - add_effect[a]
            )
            for r in removals
            for a in additions
        }

        print("\n===", field.upper(), "===")
        print("Global mean:", round(global_mean, 5))
        print(
            "Mean absolute single-swap interaction:",
            round(mean(abs(x) for x in residuals.values()), 5),
            "pp",
        )
        print(
            "Maximum single-swap interaction:",
            round(max(abs(x) for x in residuals.values()), 5),
            "pp",
        )

        print("\nTop removal contributions:")
        for r in sorted(
            removals, key=lambda x: remove_effect[x], reverse=True
        )[:3]:
            print(r, f"{remove_effect[r]:+.5f} pp")

        print("\nTop addition contributions:")
        for a in sorted(
            additions, key=lambda x: add_effect[x], reverse=True
        )[:5]:
            print(a, f"{add_effect[a]:+.5f} pp")

        print("\nLargest single-swap interactions:")
        for (r, a), value in sorted(
            residuals.items(),
            key=lambda x: abs(x[1]),
            reverse=True,
        )[:5]:
            print(f"{r}->{a}", f"{value:+.5f} pp")

    # Evaluate prediction of already calculated double swaps.
    all_doubles = doubles["results"] + recovery["results"]

    for field in fields:
        errors = []

        for row in all_doubles:
            removed, added = row["key"].split("->")
            r1, r2 = map(int, removed.split(","))
            a1, a2 = map(int, added.split(","))

            # Average both possible pairings.
            predicted = (
                matrix[r1, a1][field]
                + matrix[r1, a2][field]
                + matrix[r2, a1][field]
                + matrix[r2, a2][field]
            ) / 2

            actual = row["changes"][field]
            errors.append(actual - predicted)

        print("\nDOUBLE SWAP:", field)
        print("Samples:", len(errors))
        print(
            "MAE:",
            round(mean(abs(e) for e in errors), 5),
            "pp",
        )
        print(
            "Bias:",
            round(mean(errors), 5),
            "pp",
        )


if __name__ == "__main__":
    main()
