
# PoE BuildLab AI — Multi-Swap Planner v0.8
# Planning only. Does not execute PoB experiments.

import itertools
import os
import json
from collections import Counter
from pathlib import Path

from experiment_storage import (
    get_experiment_dir, load_report, xml_sha256
)
from build_constraints import evaluate_constraints

SKILL_GROUP = 6

SINGLE_FILES = (
    "swap_constrained.json",
    "candidate_screening_v02.json",
    "candidate_screening_v03.json",
    "screening_engine.json",
)

DOUBLE_FILES = (
    "multi_swap_results.json",
    "recovery_results.json",
    "adaptive_results.json",
)


def key_of(removes, adds):
    return (
        ",".join(map(str, sorted(removes)))
        + "->"
        + ",".join(map(str, sorted(adds)))
    )


def load_singles(directory, xml_path):
    rows = []
    seen = set()

    for filename in SINGLE_FILES:
        report = load_report(
            directory / filename, xml_path, SKILL_GROUP
        )

        for row in report["results"]:
            rid = int(row["removeId"])
            aid = int(row["addId"])
            key = f"{rid}->{aid}"

            if key in seen:
                raise RuntimeError(
                    f"Duplicate single swap: {key}"
                )

            seen.add(key)
            rows.append(row)

    return rows


def load_old_doubles(directory, xml_path):
    seen = set()
    counts = {}

    for filename in DOUBLE_FILES:
        report = load_report(
            directory / filename, xml_path, SKILL_GROUP
        )

        if report.get("complete") is not True:
            raise RuntimeError(
                f"Incomplete double-swap report: {filename}"
            )

        result_rows = report.get("results", [])
        invalid_rows = report.get("invalidTrees", [])

        counts[filename] = {
            "calculated": len(result_rows),
            "invalidTrees": len(invalid_rows),
        }

        for row in result_rows + invalid_rows:
            key = row["key"]

            if key in seen:
                raise RuntimeError(
                    f"Duplicate previous double swap: {key}"
                )

            seen.add(key)

        if report.get("errors"):
            raise RuntimeError(
                f"Unresolved errors in {filename}"
            )

        if report.get("rejected"):
            raise RuntimeError(
                f"Unresolved rejected evaluations in {filename}"
            )

    return seen, counts


def load_removal_conflicts(directory, xml_path):
    conflicts = set()

    for filename in (
        "recovery_results.json",
        "adaptive_results.json",
        "multi_swap_executed_v08.json",
    ):
        report = load_report(
            directory / filename,
            xml_path,
            SKILL_GROUP,
        )

        for row in report.get("invalidTrees", []):
            key = row["key"]
            remove_part = key.split("->", 1)[0]

            removes = tuple(sorted(
                int(x) for x in remove_part.split(",")
            ))

            # Cache only double-removal topology failures.
            if len(removes) == 2:
                conflicts.add(removes)

    return conflicts


def main():
    raw = os.environ.get("BUILD_XML")
    if not raw:
        raise RuntimeError("BUILD_XML is not set")

    xml_path = Path(raw).resolve()
    digest = xml_sha256(xml_path)
    directory = get_experiment_dir(xml_path, SKILL_GROUP)

    original = load_report(
        directory / "swap_executed.json",
        xml_path, SKILL_GROUP,
    )["baseline"]

    baseline = original["stats"]
    singles = load_singles(directory, xml_path)
    previous, counts = load_old_doubles(
        directory, xml_path
    )

    removal_conflicts = load_removal_conflicts(
        directory, xml_path
    )

    print(
        "Known incompatible removal pairs:",
        len(removal_conflicts),
    )

    seen = set()
    candidates = []
    skipped_previous = 0

    for first, second in itertools.combinations(singles, 2):
        removes = sorted([
            int(first["removeId"]),
            int(second["removeId"]),
        ])
        adds = sorted([
            int(first["addId"]),
            int(second["addId"]),
        ])

        if len(set(removes)) != 2:
            continue

        if tuple(removes) in removal_conflicts:
            continue

        if len(set(adds)) != 2:
            continue

        if set(removes) & set(adds):
            continue

        key = key_of(removes, adds)

        if key in seen:
            continue

        seen.add(key)

        if key in previous:
            skipped_previous += 1
            continue

        # Additive approximation of changes relative
        # to the ORIGINAL baseline, not another swap.
        predicted = dict(baseline)

        for field, base_value in baseline.items():
            if (
                isinstance(base_value, bool)
                or not isinstance(base_value, (int, float))
            ):
                continue

            a = first["stats"].get(field)
            b = second["stats"].get(field)

            if (
                isinstance(a, (int, float))
                and not isinstance(a, bool)
                and isinstance(b, (int, float))
                and not isinstance(b, bool)
            ):
                predicted[field] = (
                    base_value
                    + (a - base_value)
                    + (b - base_value)
                )

        row = {
            "removeId": ",".join(map(str, removes)),
            "removeName": "",
            "addId": ",".join(map(str, adds)),
            "addName": "",
            "stats": predicted,
            # Only for predicted constraint evaluation.
            # Actual tree/attribute validation happens in PoB.
            "validation": {"status": "VALID"},
        }

        checked = evaluate_constraints(original, row)
        changes = checked["changes"]

        utility = (
            changes["dps_percent"]
            + changes["ehp_percent"]
        )

        candidates.append({
            "key": key,
            "removeIds": removes,
            "addIds": adds,
            "predictedStatus": checked["status"],
            "predictedProblems": checked["problems"],
            "predictedUtility": round(utility, 6),
            "predictedDpsPercent": round(
                changes["dps_percent"], 6
            ),
            "predictedEhpPercent": round(
                changes["ehp_percent"], 6
            ),
            "sourceStatuses": [
                first["status"], second["status"]
            ],
        })

    pass_rows = sorted(
        (
            x for x in candidates
            if x["predictedStatus"] == "PASS"
        ),
        key=lambda x: (-x["predictedUtility"], x["key"]),
    )

    reject_rows = sorted(
        (
            x for x in candidates
            if x["predictedStatus"] == "REJECT"
        ),
        key=lambda x: (
            len(x["predictedProblems"]),
            -x["predictedUtility"],
            x["key"],
        ),
    )

    # Reserve a portion for exploratory combinations,
    # including predicted failures.
    chosen = []
    chosen_keys = set()

    def take(rows, limit, category):
        added = 0
        for row in rows:
            if added >= limit:
                break

            if row["key"] in chosen_keys:
                continue

            chosen_keys.add(row["key"])
            chosen.append({
                **row,
                "selectionMode": category,
            })
            added += 1

    take(pass_rows, 100, "predicted_pass")
    take(reject_rows, 60, "recovery")

    # Spread additional experiments over distinct
    # removal pairs instead of repeatedly selecting
    # the same region of the tree.
    diversity_pool = sorted(
        candidates,
        key=lambda x: (
            -x["predictedUtility"],
            x["key"],
        ),
    )

    removal_counts = Counter(
        tuple(x["removeIds"]) for x in chosen
    )

    for row in sorted(
        diversity_pool,
        key=lambda x: (
            removal_counts[tuple(x["removeIds"])],
            -x["predictedUtility"],
            x["key"],
        ),
    ):
        if len(chosen) >= 200:
            break

        if row["key"] in chosen_keys:
            continue

        chosen_keys.add(row["key"])
        chosen.append({
            **row,
            "selectionMode": "diversity",
        })
        removal_counts[tuple(row["removeIds"])] += 1

    if xml_sha256(xml_path) != digest:
        raise RuntimeError("Source XML changed")

    output = directory / "multi_swap_plan_v08.json"

    report = {
        "version": "0.8",
        "xmlPath": str(xml_path),
        "xmlSha256": digest,
        "skillGroup": SKILL_GROUP,
        "singleCount": len(singles),
        "previousDoubleCounts": counts,
        "previousDoubleKeys": len(previous),
        "generatedUnique": len(seen),
        "skippedPrevious": skipped_previous,
        "unexploredCandidates": len(candidates),
        "predictedPassCount": len(pass_rows),
        "predictedRejectCount": len(reject_rows),
        "planned": len(chosen),
        "candidates": chosen,
    }

    # Atomic report write and consistent metadata.
    from experiment_storage import save_report
    save_report(output, report)

    print("=== MULTI-SWAP PLANNER v0.8 ===")
    print("Singles loaded:", len(singles))
    print("Previously attempted doubles:", len(previous))
    print("New double candidates:", len(candidates))
    print("Predicted PASS:", len(pass_rows))
    print("Predicted REJECT:", len(reject_rows))
    print("Selected:", len(chosen))
    print("\nFIRST 10:")
    for x in chosen[:10]:
        print(
            x["key"],
            x["selectionMode"],
            "Utility:", x["predictedUtility"],
            "Status:", x["predictedStatus"],
        )

    print("\nSaved:", output)


if __name__ == "__main__":
    main()
