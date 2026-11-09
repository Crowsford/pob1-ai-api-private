
# PoE BuildLab AI — Profile-Aware Scheduler v1.8
# Separate profile queues. No PoB calls.
# Does NOT modify the legacy scheduler or executor.

import argparse
from collections import Counter
from copy import deepcopy

from build_constraints import evaluate_constraints
from build_profile import load_build_profile
from experiment_storage import get_experiment_dir, load_report
from pareto_engine import REPORTS
from profile_experiment_storage import (
    load_profile_report,
    report_path,
    save_profile_report,
)

POOL_FILE = "multi_swap_candidate_pool_fullstats_v16.json"
BATCH_FILE = "profile_batch_v18.json"
HISTORY_FILES = REPORTS + ("multi_swap_executed_v12.json",)


def candidate_row(candidate):
    return {
        "removeId": ",".join(map(str, candidate["removeIds"])),
        "addId": ",".join(map(str, candidate["addIds"])),
        "removeName": "",
        "addName": "",
        "stats": candidate["predictedStats"],
        "validation": {"status": "VALID"},
    }


def historical_state(directory, xml, group):
    done = set()
    conflicts = set()

    for filename in HISTORY_FILES:
        report = load_report(directory / filename, xml, group)

        for section in (
            "results", "invalidTrees", "invalidCandidates"
        ):
            for row in report.get(section, []):
                key = row["key"]
                if key in done:
                    raise RuntimeError(
                        f"Duplicate historical attempt: {key}"
                    )
                done.add(key)

        for row in report.get("invalidTrees", []):
            removal = row["key"].split("->", 1)[0]
            pair = tuple(sorted(
                int(x) for x in removal.split(",")
            ))
            if len(pair) == 2:
                conflicts.add(pair)

    return done, conflicts


def dominates(a, b):
    eps = 1e-7
    return (
        all(x >= y - eps for x, y in zip(a, b))
        and any(x > y + eps for x, y in zip(a, b))
    )


def metric_point(changes):
    return (
        changes["dps_percent"],
        changes["ehp_percent"],
        changes["mana_regen_percent"],
    )


def rank_candidate(candidate, checked, frontier_points):
    c = checked["changes"]
    point = metric_point(c)

    dominated = any(
        dominates(other, point)
        for other in frontier_points
    )

    # Transparent provisional ranking. The legacy scheduler
    # has a different, more advanced heuristic.
    score = (
        c["dps_percent"]
        + 0.35 * c["ehp_percent"]
        + 0.06 * c["mana_regen_percent"]
    )

    if not dominated:
        score += 2.0

    if checked["status"] == "REJECT":
        score -= 2.0 * len(checked["problems"])

    return score, not dominated


def select_diverse(candidates, count, used_removals):
    selected = []

    # First pass: prefer distinct removal pairs.
    for candidate in candidates:
        if len(selected) >= count:
            break

        removal = tuple(candidate["removeIds"])
        if removal in used_removals:
            continue

        selected.append(candidate)
        used_removals.add(removal)

    # Second pass: fill remaining slots.
    selected_keys = {x["key"] for x in selected}

    for candidate in candidates:
        if len(selected) >= count:
            break

        if candidate["key"] in selected_keys:
            continue

        selected.append(candidate)
        selected_keys.add(candidate["key"])

    return selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        default="build_profiles/bababan_test.json",
    )
    parser.add_argument(
        "--strict-recharge",
        action="store_true",
    )
    parser.add_argument("--size", type=int, default=10)
    args = parser.parse_args()

    if args.size < 1:
        raise ValueError("Batch size must be positive")

    profile = load_build_profile(args.profile)

    if args.strict_recharge:
        profile = deepcopy(profile)
        profile["build"]["name"] += " - Strict Recharge"
        profile["constraints"][
            "max_es_recharge_loss_percent"
        ] = 0.0

    xml = profile["build"]["xmlPath"]
    group = profile["build"]["skillGroup"]
    directory = get_experiment_dir(xml, group)

    output = report_path(profile, BATCH_FILE)

    if output.exists():
        raise RuntimeError(
            f"Profile batch already exists: {output}. "
            "Refusing overwrite."
        )

    pool = load_report(directory / POOL_FILE, xml, group)
    baseline = load_report(
        directory / "swap_executed.json", xml, group
    )["baseline"]

    historical = load_profile_report(
        profile, "historical_pareto_frontier.json"
    )

    frontier_points = [
        metric_point(row["changes"])
        for row in historical["frontier"]
    ]

    done, conflicts = historical_state(
        directory, xml, group
    )

    passing = []
    rejected = []
    counts = Counter()

    for candidate in pool["candidates"]:
        key = candidate["key"]

        if key in done:
            counts["already_calculated"] += 1
            continue

        removal = tuple(sorted(candidate["removeIds"]))
        if removal in conflicts:
            counts["known_topology_conflicts"] += 1
            continue

        checked = evaluate_constraints(
            baseline,
            candidate_row(candidate),
            limits=profile["constraints"],
        )

        score, pareto_candidate = rank_candidate(
            candidate, checked, frontier_points
        )

        result = dict(candidate)
        # Keep the original prediction for comparison.
        result["legacyPredictedStatus"] = candidate[
            "predictedStatus"
        ]
        result["predictedStatus"] = checked["status"]
        result["predictedProblems"] = checked["problems"]
        result["predictedDpsPercent"] = round(
            checked["changes"]["dps_percent"], 6
        )
        result["predictedEhpPercent"] = round(
            checked["changes"]["ehp_percent"], 6
        )
        result["predictedManaRegenPercent"] = round(
            checked["changes"]["mana_regen_percent"], 6
        )
        result["profileRankingScore"] = round(score, 6)
        result["paretoCandidate"] = pareto_candidate

        counts[checked["status"]] += 1

        if checked["status"] == "PASS":
            passing.append(result)
        else:
            # Explore reasonably promising rejected predictions.
            if (
                len(checked["problems"]) <= 2
                and checked["changes"]["dps_percent"] >= 0
            ):
                rejected.append(result)

    passing.sort(
        key=lambda x: (-x["profileRankingScore"], x["key"])
    )
    rejected.sort(
        key=lambda x: (-x["profileRankingScore"], x["key"])
    )

    desired_reject = (
        max(1, args.size // 5)
        if args.size >= 5 else 0
    )
    desired_pass = args.size - desired_reject

    used_removals = set()
    selected = select_diverse(
        passing, desired_pass, used_removals
    )
    selected += select_diverse(
        rejected, desired_reject, used_removals
    )

    if len(selected) < args.size:
        selected_keys = {x["key"] for x in selected}
        remaining = [
            x for x in passing + rejected
            if x["key"] not in selected_keys
        ]
        selected += remaining[:args.size - len(selected)]

    report = {
        "version": "1.8",
        "poolFile": POOL_FILE,
        "historyFiles": list(HISTORY_FILES),
        "historicalAttempts": len(done),
        "knownRemovalConflicts": len(conflicts),
        "profilePredictedPass": counts["PASS"],
        "profilePredictedReject": counts["REJECT"],
        "planned": len(selected),
        "candidates": selected,
    }

    saved = save_profile_report(profile, BATCH_FILE, report)

    print("=== PROFILE-AWARE SCHEDULER v1.8 ===")
    print("Profile:", profile["build"]["name"])
    print("Pool candidates:", len(pool["candidates"]))
    print("Historical attempts:", len(done))
    print("Known removal conflicts:", len(conflicts))
    print("Available predicted PASS:", counts["PASS"])
    print("Available predicted REJECT:", counts["REJECT"])
    print("Selected:", len(selected))

    print("\nSELECTED CANDIDATES:")
    for row in selected:
        print(
            row["key"],
            row["predictedStatus"],
            "DPS:", row["predictedDpsPercent"],
            "EHP:", row["predictedEhpPercent"],
            "Score:", row["profileRankingScore"],
        )

    print("\nSaved:", saved)
    print("Legacy batch: UNCHANGED")
    print("PoB calls: 0")


if __name__ == "__main__":
    main()
