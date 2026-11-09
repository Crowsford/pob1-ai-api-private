
# PoE BuildLab AI — Multi-Swap Planner v1.0
# Full-stat-profile diversity; no PoB execution.

import itertools
import os
from collections import Counter, defaultdict
from pathlib import Path

from experiment_storage import (
    get_experiment_dir,
    load_report,
    save_report,
    xml_sha256,
)
from build_constraints import evaluate_constraints
from multi_swap_planner_v09 import (
    load_singles,
    load_old_doubles,
    load_removal_conflicts,
    key_of,
)

SKILL_GROUP = 6
MAX_CANDIDATES = 200
EXPLORATION_SIZE = 40

PREVIOUS_EXECUTIONS = (
    "multi_swap_executed_v08.json",
    "multi_swap_executed_v09.json",
)


def previous_attempts(directory, xml_path):
    previous, counts = load_old_doubles(
        directory, xml_path
    )

    for filename in PREVIOUS_EXECUTIONS:
        report = load_report(
            directory / filename, xml_path, SKILL_GROUP
        )

        rows = (
            report.get("results", [])
            + report.get("invalidTrees", [])
            + report.get("invalidCandidates", [])
        )

        keys = [row["key"] for row in rows]

        if len(keys) != len(set(keys)):
            raise RuntimeError(
                f"Duplicate keys in {filename}"
            )

        if previous.intersection(keys):
            raise RuntimeError(
                f"Overlapping history in {filename}"
            )

        previous.update(keys)
        counts[filename] = {"processed": len(keys)}

    return previous, counts


def predict_stats(baseline, first, second):
    predicted = dict(baseline)

    for field, base in baseline.items():
        if isinstance(base, bool) or not isinstance(
            base, (int, float)
        ):
            continue

        a = first["stats"].get(field)
        b = second["stats"].get(field)

        if all(
            isinstance(v, (int, float))
            and not isinstance(v, bool)
            for v in (a, b)
        ):
            predicted[field] = base + (a - base) + (b - base)

    return predicted


def profile_key(stats):
    # Profile similarity is approximate, not proof
    # of identical passive-tree behavior.
    return tuple(
        (field, round(float(value), 4))
        for field, value in sorted(stats.items())
        if isinstance(value, (int, float))
        and not isinstance(value, bool)
    )


def rank_candidate(candidate):
    return (
        -candidate["predictedScore"],
        candidate["key"],
    )


def select_diverse(pool, limit, selected, used_keys, mode):
    # Group by full predicted stat profile.
    by_profile = defaultdict(list)

    for candidate in pool:
        if candidate["key"] in used_keys:
            continue
        by_profile[candidate["profile"]].append(candidate)

    # Pick the best representative from each profile.
    representatives = [
        min(rows, key=rank_candidate)
        for rows in by_profile.values()
    ]

    representatives.sort(key=rank_candidate)

    removal_counts = Counter(
        tuple(row["removeIds"]) for row in selected
    )

    # First pass: favor different removal pairs.
    deferred = []

    for candidate in representatives:
        if len(selected) >= limit:
            break

        removal_pair = tuple(candidate["removeIds"])

        if removal_counts[removal_pair] >= 2:
            deferred.append(candidate)
            continue

        chosen = dict(candidate)
        chosen["selectionMode"] = mode
        chosen.pop("profile")

        selected.append(chosen)
        used_keys.add(chosen["key"])
        removal_counts[removal_pair] += 1

    # Second pass: allow additional removal-pair coverage.
    for candidate in deferred:
        if len(selected) >= limit:
            break

        if candidate["key"] in used_keys:
            continue

        chosen = dict(candidate)
        chosen["selectionMode"] = mode
        chosen.pop("profile")

        selected.append(chosen)
        used_keys.add(chosen["key"])

    # Third pass: preserve alternative topologies if needed.
    if len(selected) < limit:
        for candidate in sorted(pool, key=rank_candidate):
            if len(selected) >= limit:
                break

            if candidate["key"] in used_keys:
                continue

            chosen = dict(candidate)
            chosen["selectionMode"] = mode + "_alternate"
            chosen.pop("profile")

            selected.append(chosen)
            used_keys.add(chosen["key"])


def main():
    raw = os.environ.get("BUILD_XML")
    if not raw:
        raise RuntimeError("BUILD_XML is not set")

    xml_path = Path(raw).resolve()
    digest = xml_sha256(xml_path)
    directory = get_experiment_dir(
        xml_path, SKILL_GROUP
    )

    original = load_report(
        directory / "swap_executed.json",
        xml_path,
        SKILL_GROUP,
    )["baseline"]

    baseline = original["stats"]

    singles = load_singles(directory, xml_path)

    previous, counts = previous_attempts(
        directory, xml_path
    )

    conflicts = load_removal_conflicts(
        directory, xml_path
    )

    # Every combination is deduplicated by final
    # removal/addition sets, not by source pairing.
    unique = {}

    for first, second in itertools.combinations(singles, 2):
        removes = sorted(
            (int(first["removeId"]), int(second["removeId"]))
        )
        adds = sorted(
            (int(first["addId"]), int(second["addId"]))
        )

        if len(set(removes)) != 2:
            continue
        if len(set(adds)) != 2:
            continue
        if set(removes) & set(adds):
            continue
        if tuple(removes) in conflicts:
            continue

        key = key_of(removes, adds)

        if key in previous:
            continue

        predicted = predict_stats(
            baseline, first, second
        )

        row = {
            "removeId": ",".join(map(str, removes)),
            "removeName": "",
            "addId": ",".join(map(str, adds)),
            "addName": "",
            "stats": predicted,
            "validation": {"status": "VALID"},
        }

        checked = evaluate_constraints(
            original, row
        )

        changes = checked["changes"]

        utility = (
            changes["dps_percent"]
            + changes["ehp_percent"]
        )

        # Secondary reward for mana regeneration.
        mana_change = changes.get(
            "mana_regen_percent", 0
        ) or 0

        score = utility + 0.02 * mana_change

        candidate = {
            "key": key,
            "removeIds": removes,
            "addIds": adds,
            "predictedStatus": checked["status"],
            "predictedProblems": checked["problems"],
            "predictedUtility": round(utility, 6),
            "predictedScore": round(score, 6),
            "predictedDpsPercent": round(
                changes["dps_percent"], 6
            ),
            "predictedEhpPercent": round(
                changes["ehp_percent"], 6
            ),
            "predictedManaRegenPercent": round(
                mana_change, 6
            ),
            "profile": profile_key(predicted),
        }

        old = unique.get(key)

        # Multiple source pairings can predict
        # different outcomes for the same final swap.
        if old is None or score > old["predictedScore"]:
            unique[key] = candidate

    candidates = list(unique.values())

    passing = [
        x for x in candidates
        if x["predictedStatus"] == "PASS"
    ]

    rejected = [
        x for x in candidates
        if x["predictedStatus"] == "REJECT"
    ]

    selected = []
    used_keys = set()

    select_diverse(
        passing,
        MAX_CANDIDATES - EXPLORATION_SIZE,
        selected,
        used_keys,
        "predicted_pass",
    )

    # Recovery candidates can expose interactions
    # that the additive model fails to predict.
    select_diverse(
        rejected,
        MAX_CANDIDATES,
        selected,
        used_keys,
        "exploration",
    )

    if xml_sha256(xml_path) != digest:
        raise RuntimeError("Source XML changed")

    output = directory / "multi_swap_plan_v10.json"

    report = {
        "version": "1.0",
        "xmlPath": str(xml_path),
        "xmlSha256": digest,
        "skillGroup": SKILL_GROUP,
        "singleCount": len(singles),
        "previousDoubleCounts": counts,
        "previousDoubleKeys": len(previous),
        "knownRemovalConflicts": len(conflicts),
        "unexploredCandidates": len(candidates),
        "predictedPassCount": len(passing),
        "predictedRejectCount": len(rejected),
        "predictedUniqueProfiles": len({
            x["profile"] for x in candidates
        }),
        "planned": len(selected),
        "candidates": selected,
    }

    save_report(output, report)

    print("=== MULTI-SWAP PLANNER v1.0 ===")
    print("Singles:", len(singles))
    print("Previous doubles:", len(previous))
    print("Removal conflicts:", len(conflicts))
    print("New candidates:", len(candidates))
    print("Predicted PASS:", len(passing))
    print("Predicted REJECT:", len(rejected))
    print(
        "Unique predicted profiles:",
        report["predictedUniqueProfiles"],
    )
    print("Selected:", len(selected))
    print(
        "Distinct removal pairs:",
        len({
            tuple(x["removeIds"]) for x in selected
        }),
    )
    print("\nFIRST 10:")

    for x in selected[:10]:
        print(
            x["key"],
            x["selectionMode"],
            "Score:", x["predictedScore"],
            "Mana:", x["predictedManaRegenPercent"],
        )

    print("\nSaved:", output)


if __name__ == "__main__":
    main()
