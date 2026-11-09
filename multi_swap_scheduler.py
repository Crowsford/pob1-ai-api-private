
# PoE BuildLab AI — Dynamic Multi-Swap Scheduler v1.2
# Plans experiments from the full candidate pool.
# Does not execute PoB.

import argparse
import os
from collections import Counter
from pathlib import Path

from experiment_storage import (
    get_experiment_dir,
    load_report,
    save_report,
    xml_sha256,
)
from pareto_engine import assess_candidate, REPORTS
from interaction_model import (
    corrected_changes,
    correction_details,
)

SKILL_GROUP = 6
POOL_FILE = "multi_swap_candidate_pool.json"
OUTPUT_FILE = "multi_swap_batch_v12.json"


def all_history(directory, xml_path):
    done = set()
    removal_conflicts = set()
    invalid_risk = Counter()
    constraint_risk = Counter()

    for filename in REPORTS + ("multi_swap_executed_v12.json",):
        report = load_report(
            directory / filename, xml_path, SKILL_GROUP
        )

        rows = (
            report.get("results", [])
            + report.get("invalidTrees", [])
            + report.get("invalidCandidates", [])
        )

        for invalid in report.get("invalidTrees", []):
            remove_text = invalid["key"].split("->", 1)[0]
            removal_pair = tuple(sorted(
                int(x) for x in remove_text.split(",")
            ))
            if len(removal_pair) == 2:
                removal_conflicts.add(removal_pair)

        for row in rows:
            key = row["key"]

            if key in done:
                raise RuntimeError(
                    f"Duplicate experiment in history: {key}"
                )

            done.add(key)

            removal_text, addition_text = key.split("->")
            removals = tuple(sorted(
                int(x) for x in removal_text.split(",")
            ))
            additions = [
                int(x) for x in addition_text.split(",")
            ]

            if row in report.get("invalidCandidates", []):
                for add_id in additions:
                    invalid_risk[(removals, add_id)] += 1

            elif row.get("status") == "REJECT":
                problems = row.get("problems", [])

                # Track violation types separately.
                for add_id in additions:
                    for problem in problems:
                        constraint_risk[
                            (removals, add_id, problem)
                        ] += 1

    return done, invalid_risk, constraint_risk, removal_conflicts


def values(candidate):
    return {
        "dps_percent": candidate["predictedDpsPercent"],
        "ehp_percent": candidate["predictedEhpPercent"],
        "mana_regen_percent":
            candidate["predictedManaRegenPercent"],
    }


def risk_penalty(candidate, invalid_risk, constraint_risk):
    removals = tuple(candidate["removeIds"])

    invalid = sum(
        invalid_risk[(removals, add)]
        for add in candidate["addIds"]
    )

    constraints = sum(
        count
        for (rem, add, problem), count
        in constraint_risk.items()
        if rem == removals and add in candidate["addIds"]
    )

    return 5.0 * invalid + 0.5 * constraints


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=20)
    args = parser.parse_args()

    if args.size < 1:
        parser.error("--size must be positive")

    raw = os.environ.get("BUILD_XML")
    if not raw:
        raise RuntimeError("BUILD_XML is not set")

    xml_path = Path(raw).resolve()
    digest = xml_sha256(xml_path)
    directory = get_experiment_dir(
        xml_path, SKILL_GROUP
    )

    pool = load_report(
        directory / POOL_FILE,
        xml_path,
        SKILL_GROUP,
    )

    if pool.get("version") != "1.2-pool":
        raise RuntimeError("Unexpected candidate pool version")

    if pool["candidateCount"] != len(pool["candidates"]):
        raise RuntimeError("Candidate pool count mismatch")

    frontier = load_report(
        directory / "pareto_frontier.json",
        xml_path,
        SKILL_GROUP,
    )["frontier"]

    done, invalid_risk, constraint_risk, removal_conflicts = all_history(
        directory, xml_path
    )

    # Do not overwrite a batch that is not yet completed.
    batch_path = directory / OUTPUT_FILE

    if batch_path.exists():
        existing = load_report(
            batch_path, xml_path, SKILL_GROUP
        )
        if existing.get("version") != "1.2":
            raise RuntimeError("Unexpected existing batch version")

        unfinished = [
            c["key"] for c in existing["candidates"]
            if c["key"] not in done
        ]
        if unfinished:
            raise RuntimeError(
                f"Existing batch has {len(unfinished)} "
                "unfinished experiments. Resume executor first."
            )

    pending = [
        c for c in pool["candidates"]
        if c["key"] not in done
        and tuple(c["removeIds"]) not in removal_conflicts
    ]

    print(
        "Known conflicting removal pairs:",
        len(removal_conflicts),
    )

    ranked = []

    for candidate in pending:
        calibrated = corrected_changes(
            values(candidate), candidate["addIds"]
        )

        assessment = assess_candidate(
            calibrated, frontier
        )

        penalty = risk_penalty(
            candidate, invalid_risk, constraint_risk
        )

        score = (
            3.0 * int(assessment["isParetoCandidate"])
            + 1.5 * assessment["dominatesFrontierCount"]
            - 0.8 * assessment["dominatedByCount"]
            + 0.15 * calibrated["dps_percent"]
            + 0.15 * candidate["predictedEhpPercent"]
            + 0.025 * candidate["predictedManaRegenPercent"]
            - penalty
        )

        ranked.append({
            **candidate,
            "paretoPrediction": assessment,
            "rankingScore": round(score, 6),
            "calibratedDpsPercent": round(
                calibrated["dps_percent"], 6
            ),
            "interactionModel": correction_details(
                candidate["addIds"]
            ),
        })

    passing = sorted(
        (
            c for c in ranked
            if c["predictedStatus"] == "PASS"
        ),
        key=lambda c: (-c["rankingScore"], c["key"]),
    )
    rejected = sorted(
        (
            c for c in ranked
            if c["predictedStatus"] == "REJECT"
        ),
        key=lambda c: (-c["rankingScore"], c["key"]),
    )

    selected = []
    selected_keys = set()
    removal_counts = Counter()
    profile_counts = Counter()

    def profile(candidate):
        v = values(candidate)
        return tuple(
            round(v[k], 4)
            for k in (
                "dps_percent",
                "ehp_percent",
                "mana_regen_percent",
            )
        )

    def take(candidates, quota, mode):
        added = 0

        while added < quota:
            available = [
                c for c in candidates
                if c["key"] not in selected_keys
            ]

            if not available:
                break

            # Greedy selection with a diversity penalty.
            winner = max(
                available,
                key=lambda c: (
                    c["rankingScore"]
                    - 1.5 * removal_counts[
                        tuple(c["removeIds"])
                    ]
                    - 2.0 * profile_counts[profile(c)],
                    c["key"],
                ),
            )

            selected.append({
                **winner,
                "selectionMode": mode,
            })
            selected_keys.add(winner["key"])
            removal_counts[
                tuple(winner["removeIds"])
            ] += 1
            profile_counts[profile(winner)] += 1
            added += 1

    # Approximately 80% exploitation and 20% exploration.
    exploration = max(1, args.size // 5)
    exploitation = args.size - exploration

    take(passing, exploitation, "pareto_guided")
    take(rejected, exploration, "exploration")

    # Fill any remaining positions from whichever pool
    # still has candidates available.
    if len(selected) < args.size:
        take(
            ranked,
            args.size - len(selected),
            "fallback",
        )

    if xml_sha256(xml_path) != digest:
        raise RuntimeError("Build XML changed")

    output = directory / OUTPUT_FILE

    report = {
        "version": "1.2",
        "xmlPath": str(xml_path),
        "xmlSha256": digest,
        "skillGroup": SKILL_GROUP,
        "poolCount": len(pool["candidates"]),
        "historicalAttempts": len(done),
        "remainingCandidates": len(pending),
        "planned": len(selected),
        "candidates": selected,
    }

    save_report(output, report)

    print("=== DYNAMIC MULTI-SWAP SCHEDULER v1.2 ===")
    print("Full pool:", len(pool["candidates"]))
    print("Historical attempts:", len(done))
    print("Available:", len(pending))
    print("Batch selected:", len(selected))
    print(
        "Interaction-corrected candidates:",
        sum(
            x["interactionModel"]["verified"]
            for x in selected
        ),
    )
    print("Predicted PASS:", sum(
        c["predictedStatus"] == "PASS"
        for c in selected
    ))
    print("Predicted REJECT:", sum(
        c["predictedStatus"] == "REJECT"
        for c in selected
    ))
    print("Distinct removal pairs:", len({
        tuple(c["removeIds"]) for c in selected
    }))
    print("\nFIRST 10:")

    for c in selected[:10]:
        print(
            c["key"],
            c["selectionMode"],
            "Score:", c["rankingScore"],
            "Pareto:",
            c["paretoPrediction"]["isParetoCandidate"],
        )

    print("\nSaved:", output)


if __name__ == "__main__":
    main()
