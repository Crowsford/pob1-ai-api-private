
# PoE BuildLab AI — Adaptive Multi-Swap Queue v1.1
# Reorders pending v1.0 candidates using the measured
# Pareto frontier. Does NOT execute PoB.

import os
from collections import Counter
from pathlib import Path

from experiment_storage import (
    get_experiment_dir,
    load_report,
    save_report,
    xml_sha256,
)
from pareto_engine import assess_candidate

SKILL_GROUP = 6


def predicted_changes(candidate):
    return {
        "dps_percent": candidate["predictedDpsPercent"],
        "ehp_percent": candidate["predictedEhpPercent"],
        "mana_regen_percent":
            candidate["predictedManaRegenPercent"],
    }


def signature(candidate):
    changes = predicted_changes(candidate)
    return tuple(
        round(changes[field], 4)
        for field in (
            "dps_percent",
            "ehp_percent",
            "mana_regen_percent",
        )
    )


def main():
    raw = os.environ.get("BUILD_XML")
    if not raw:
        raise RuntimeError("BUILD_XML is not set")

    xml_path = Path(raw).resolve()
    digest = xml_sha256(xml_path)
    directory = get_experiment_dir(
        xml_path, SKILL_GROUP
    )

    old_plan = load_report(
        directory / "multi_swap_plan_v10.json",
        xml_path, SKILL_GROUP,
    )

    old_results = load_report(
        directory / "multi_swap_executed_v10.json",
        xml_path, SKILL_GROUP,
    )

    pareto = load_report(
        directory / "pareto_frontier.json",
        xml_path, SKILL_GROUP,
    )

    completed_rows = (
        old_results.get("results", [])
        + old_results.get("invalidTrees", [])
        + old_results.get("invalidCandidates", [])
    )

    completed_keys = [x["key"] for x in completed_rows]

    if len(completed_keys) != len(set(completed_keys)):
        raise RuntimeError("Duplicate completed experiments")

    completed = set(completed_keys)
    old_keys = [x["key"] for x in old_plan["candidates"]]

    if len(old_keys) != len(set(old_keys)):
        raise RuntimeError("Duplicate planned experiments")

    if not completed.issubset(set(old_keys)):
        raise RuntimeError("Completed experiments not in plan")

    pending = [
        x for x in old_plan["candidates"]
        if x["key"] not in completed
    ]

    for candidate in pending:
        assessment = assess_candidate(
            predicted_changes(candidate),
            pareto["frontier"],
        )
        candidate["paretoPrediction"] = assessment
        candidate["predictedProfile"] = list(
            signature(candidate)
        )

    # Do not reprioritize already executed v1.1 experiments.
    executed_v11 = load_report(
        directory / "multi_swap_executed_v11.json",
        xml_path, SKILL_GROUP,
    )
    done_rows = (
        executed_v11.get("results", [])
        + executed_v11.get("invalidTrees", [])
        + executed_v11.get("invalidCandidates", [])
    )
    done_keys = [row["key"] for row in done_rows]
    if len(done_keys) != len(set(done_keys)):
        raise RuntimeError("Duplicate v1.1 results")
    if not set(done_keys).issubset({x["key"] for x in pending}):
        raise RuntimeError("Unexpected v1.1 completed key")

    # Learn from previous failed experiments.
    invalid_risk = Counter()
    constraint_risk = Counter()

    def record_risk(row, counter):
        removal_part, addition_part = row["key"].split("->")
        removals = tuple(sorted(
            int(x) for x in removal_part.split(",")
        ))
        additions = [
            int(x) for x in addition_part.split(",")
        ]
        for add_id in additions:
            counter[(removals, add_id)] += 1

    for row in executed_v11.get("invalidCandidates", []):
        record_risk(row, invalid_risk)

    for row in executed_v11.get("results", []):
        if row["status"] == "REJECT":
            record_risk(row, constraint_risk)

    print(
        "Learned risk patterns:",
        len(invalid_risk), "invalid,",
        len(constraint_risk), "constraint-related",
    )

    selected = []
    remaining = [
        x for x in pending if x["key"] not in set(done_keys)
    ]

    removal_counts = Counter()
    profile_counts = Counter()

    # 80% exploitation, 20% exploration when
    # both categories are available.
    while remaining:
        index = len(selected)
        prefer_exploration = (index % 5 == 4)

        pool = [
            x for x in remaining
            if (x["predictedStatus"] == "REJECT")
            == prefer_exploration
        ]

        if not pool:
            pool = remaining

        def priority(candidate):
            a = candidate["paretoPrediction"]
            removal = tuple(candidate["removeIds"])
            profile = signature(candidate)

            score = (
                4.0 * int(a["isParetoCandidate"])
                + 2.0 * a["dominatesFrontierCount"]
                - 1.0 * a["dominatedByCount"]
                + 0.20 * candidate["predictedDpsPercent"]
                + 0.20 * candidate["predictedEhpPercent"]
                + 0.03 * candidate[
                    "predictedManaRegenPercent"
                ]
                - 1.5 * removal_counts[removal]
                - 2.0 * profile_counts[profile]
                - 5.0 * sum(
                    invalid_risk[
                        (removal, add_id)
                    ]
                    for add_id in candidate["addIds"]
                )
                - 0.8 * sum(
                    constraint_risk[
                        (removal, add_id)
                    ]
                    for add_id in candidate["addIds"]
                )
            )

            # An equally ranked candidate with fewer
            # prior visits to its removal pair wins.
            return (
                score,
                -removal_counts[removal],
                -profile_counts[profile],
                candidate["key"],
            )

        winner = max(pool, key=priority)
        remaining.remove(winner)

        selected.append({
            **winner,
            "selectionMode": (
                "exploration"
                if winner["predictedStatus"] == "REJECT"
                else "pareto_guided"
            ),
        })

        removal_counts[
            tuple(winner["removeIds"])
        ] += 1

        profile_counts[
            signature(winner)
        ] += 1

    # Preserve the fixed plan universe. The executor skips these
    # completed keys regardless of their position in the queue.
    selected.extend(
        dict(candidate, selectionMode="already_completed")
        for candidate in pending
        if candidate["key"] in set(done_keys)
    )
    if {x["key"] for x in selected} != {
        x["key"] for x in pending
    }:
        raise RuntimeError("Plan key set changed")

    if xml_sha256(xml_path) != digest:
        raise RuntimeError("Build XML changed")

    output = directory / "multi_swap_plan_v11.json"

    report = {
        "version": "1.1",
        "xmlPath": str(xml_path),
        "xmlSha256": digest,
        "skillGroup": SKILL_GROUP,
        "sourcePlan": "multi_swap_plan_v10.json",
        "sourceFrontier": "pareto_frontier.json",
        "previouslyCompleted": len(completed),
        "planned": len(selected),
        "candidates": selected,
    }

    save_report(output, report)

    print("=== ADAPTIVE MULTI-SWAP QUEUE v1.1 ===")
    print("Original plan:", len(old_keys))
    print("Previously completed:", len(completed))
    print("Remaining:", len(pending))
    print("New queue:", len(selected))

    print(
        "Predicted Pareto candidates:",
        sum(
            x["paretoPrediction"]["isParetoCandidate"]
            for x in selected
        ),
    )

    print(
        "Exploration candidates:",
        sum(
            x["selectionMode"] == "exploration"
            for x in selected
        ),
    )

    print(
        "Distinct removal pairs:",
        len({
            tuple(x["removeIds"]) for x in selected
        }),
    )

    print("\nFIRST 10:")

    for candidate in selected[:10]:
        assessment = candidate["paretoPrediction"]

        print(
            candidate["key"],
            candidate["selectionMode"],
            "Pareto:", assessment["isParetoCandidate"],
            "Dominates:",
            assessment["dominatesFrontierCount"],
            "Dominated by:",
            assessment["dominatedByCount"],
        )

    print("\nSaved:", output)


if __name__ == "__main__":
    main()
