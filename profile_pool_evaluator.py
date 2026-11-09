
# PoE BuildLab AI — Profile Pool Evaluator v1.7
# Read-only comparison of predictions under two profiles.

import os
from collections import Counter
from copy import deepcopy
from pathlib import Path

from build_constraints import evaluate_constraints
from build_profile import load_build_profile
from experiment_storage import get_experiment_dir, load_report

POOL_FILE = "multi_swap_candidate_pool_fullstats_v16.json"
BASELINE_FILE = "swap_executed.json"


def make_row(candidate):
    return {
        "removeId": ",".join(
            str(x) for x in candidate["removeIds"]
        ),
        "addId": ",".join(
            str(x) for x in candidate["addIds"]
        ),
        "removeName": "",
        "addName": "",
        "stats": candidate["predictedStats"],
        # Prediction is not proof of tree validity.
        "validation": {"status": "VALID"},
    }


def main():
    profile = load_build_profile(
        "build_profiles/bababan_test.json"
    )

    strict = deepcopy(profile)
    strict["constraints"][
        "max_es_recharge_loss_percent"
    ] = 0.0

    xml = Path(profile["build"]["xmlPath"])
    group = profile["build"]["skillGroup"]
    directory = get_experiment_dir(xml, group)

    pool = load_report(
        directory / POOL_FILE, xml, group
    )
    baseline = load_report(
        directory / BASELINE_FILE, xml, group
    )["baseline"]

    counters = Counter()
    changed = []
    mismatches = []
    reason_changes = Counter()

    candidates = pool["candidates"]

    if len({x["key"] for x in candidates}) != len(candidates):
        raise RuntimeError("Duplicate candidate keys")

    print("=== PROFILE POOL EVALUATOR v1.7 ===")
    print("Candidates:", len(candidates))

    for candidate in candidates:
        row = make_row(candidate)

        normal = evaluate_constraints(
            baseline,
            row,
            limits=profile["constraints"],
        )

        restrictive = evaluate_constraints(
            baseline,
            row,
            limits=strict["constraints"],
        )

        counters["normal_" + normal["status"]] += 1
        counters["strict_" + restrictive["status"]] += 1

        if normal["status"] != candidate["predictedStatus"]:
            mismatches.append({
                "key": candidate["key"],
                "stored": candidate["predictedStatus"],
                "calculated": normal["status"],
            })

        if normal["problems"] != candidate["predictedProblems"]:
            counters["problem_mismatches"] += 1

        if normal["status"] != restrictive["status"]:
            counters["changed_statuses"] += 1

            changed.append({
                "key": candidate["key"],
                "before": normal["status"],
                "after": restrictive["status"],
                "dps": normal["changes"]["dps_percent"],
                "ehp": normal["changes"]["ehp_percent"],
                "recharge": normal["changes"][
                    "es_recharge_percent"
                ],
            })

        for problem in restrictive["problems"]:
            if problem not in normal["problems"]:
                reason_changes[problem] += 1

    print("\nORIGINAL PROFILE")
    print("PASS:", counters["normal_PASS"])
    print("REJECT:", counters["normal_REJECT"])
    print("Stored status mismatches:", len(mismatches))
    print(
        "Stored problem mismatches:",
        counters["problem_mismatches"],
    )

    print("\nSTRICT RECHARGE PROFILE")
    print("PASS:", counters["strict_PASS"])
    print("REJECT:", counters["strict_REJECT"])
    print("Changed statuses:", counters["changed_statuses"])

    print("\nNEW REJECTION REASONS")
    for problem, count in reason_changes.most_common():
        print(problem, count)

    print("\nFIRST 15 STATUS CHANGES")
    for item in changed[:15]:
        print(
            item["key"],
            item["before"], "->", item["after"],
            "DPS:", round(item["dps"], 4),
            "EHP:", round(item["ehp"], 4),
            "ES Recharge:", round(item["recharge"], 4),
        )

    print("\nORIGINAL-PROFILE MISMATCH EXAMPLES")
    for item in mismatches[:10]:
        print(item)

    print("\nPoB calls: 0")
    print("Files modified: 0")

    if mismatches or counters["problem_mismatches"]:
        raise RuntimeError(
            "Original pool predictions were not reproduced"
        )

    print("Legacy prediction compatibility: PASS")


if __name__ == "__main__":
    main()
