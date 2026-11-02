
# PoE BuildLab AI — Adaptive Queue v0.5
# Prediction is approximate. PoB remains authoritative.

from build_constraints import evaluate_constraints

import json
import math
import os
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from experiment_storage import (
    get_experiment_dir,
    load_report,
    xml_sha256,
)
from screening_engine import SOURCES, SKILL_GROUP, build_plan, discover


FIELDS = (
    "combinedDPS",
    "totalEHP",
    "energyShield",
    "energyShieldRecharge",
    "manaRegen",
    "manaUnreserved",
    "manaCost",
    "blockChance",
    "spellBlockChance",
    "blockChanceMax",
    "spellBlockChanceMax",
    "fireResist",
    "coldResist",
    "lightningResist",
    "chaosResist",
    "spellSuppressionChance",
    "effectiveSpellSuppressionChance",
    "spellSuppressionEffect",
)



def number(stats, field):
    value = stats.get(field)
    return float(value) if isinstance(value, (int, float)) else None


def main():
    raw = os.environ.get("BUILD_XML")
    if not raw:
        raise RuntimeError("BUILD_XML is not set")

    xml_path = Path(raw).resolve()
    directory = get_experiment_dir(xml_path, SKILL_GROUP)
    digest = xml_sha256(xml_path)

    candidates = load_report(
        directory / "candidate_scores.json",
        xml_path, SKILL_GROUP,
    )
    if (
        candidates.get("complete") is not True
        or candidates.get("errors")
        or len(candidates["scores"]) != candidates["candidateCount"]
    ):
        raise RuntimeError("Incomplete candidate scores")

    executed = load_report(
        directory / "swap_executed.json",
        xml_path, SKILL_GROUP,
    )
    baseline = executed["baseline"]["stats"]
    additions = {int(x["id"]): x for x in candidates["scores"]}

    plan = build_plan(discover(xml_path))
    history = []
    completed = set()

    for filename in SOURCES + ("screening_engine.json",):
        report = load_report(directory / filename, xml_path, SKILL_GROUP)

        for row in report["results"]:
            key = f"{int(row['removeId'])}->{int(row['addId'])}"
            if key in completed:
                raise RuntimeError(f"Duplicate historical key: {key}")
            completed.add(key)
            history.append(row)

        for row in report.get("invalidTrees", []):
            key = row["key"]
            if key in completed:
                raise RuntimeError(f"Duplicate historical key: {key}")
            completed.add(key)

    if set(additions) != {int(x["addId"]) for x in plan}:
        raise RuntimeError("Candidate scores and discovery differ")

    # Estimate the effect of each removal from actual swaps,
    # subtracting the standalone effect of the added node.
    observations = defaultdict(lambda: defaultdict(list))
    add_counts = Counter()
    remove_counts = Counter()

    for row in history:
        rid, aid = int(row["removeId"]), int(row["addId"])
        add_counts[aid] += 1
        remove_counts[rid] += 1

        add_stats = additions[aid]["stats"]
        swap_stats = row["stats"]

        for field in FIELDS:
            a = number(add_stats, field)
            s = number(swap_stats, field)
            if a is not None and s is not None:
                observations[rid][field].append(s - a)

    effects = {
        rid: {
            field: statistics.median(values)
            for field, values in fields.items()
        }
        for rid, fields in observations.items()
    }

    def predict(pair):
        rid, aid = pair["removeId"], pair["addId"]
        added = additions[aid]["stats"]
        removal = effects.get(rid, {})
        output = {}

        for field in FIELDS:
            value = number(added, field)
            if value is not None:
                output[field] = value + removal.get(field, 0.0)

        return output

    def change(prediction, field):
        base = number(baseline, field)
        candidate = prediction.get(field)
        if base is None or candidate is None or base == 0:
            return 0.0
        return 100.0 * (candidate / base - 1.0)

    
    def assess(pair):
        predicted = predict(pair)

        # The predictor only ranks experiments.
        # This validation flag is a placeholder:
        # real validation must be performed by PoB.
        row = {
            "removeId": pair["removeId"],
            "removeName": pair["removeName"],
            "addId": pair["addId"],
            "addName": pair["addName"],
            "stats": predicted,
            "validation": {"status": "VALID"},
        }

        checked = evaluate_constraints(
            {"stats": baseline},
            row,
        )

        dps = checked["changes"]["dps_percent"]
        ehp = checked["changes"]["ehp_percent"]

        # Utility and feasibility are independent.
        utility = dps + ehp

        violations = checked["problems"]
        feasibility = (
            "PREDICTED_PASS"
            if not violations
            else "PREDICTED_REJECT"
        )

        # Candidate ranking, NOT a replacement
        # for the authoritative constraint check.
        penalty = 5.0 * len(violations)

        priority = utility - penalty

        rid = pair["removeId"]
        observations_count = remove_counts[rid]

        return {
            "priority": priority,
            "utility": utility,
            "feasibility": feasibility,
            "violations": violations,
            "removalObservations": observations_count,
        }

    def score(pair):
        return assess(pair)["priority"]



    remaining = [
        x for x in plan
        if x["key"] not in completed
    ]

    # A deterministic ranked queue.
    exploitation = sorted(
        remaining,
        key=lambda x: (-score(x), x["key"]),
    )
    exploration = sorted(
        remaining,
        key=lambda x: (
            add_counts[x["addId"]],
            -score(x),
            x["key"],
        ),
    )

    # Diversity: round-robin across removal nodes.
    buckets = defaultdict(list)
    for x in remaining:
        buckets[x["removeId"]].append(x)

    for rows in buckets.values():
        rows.sort(
            key=lambda x: (
                add_counts[x["addId"]],
                -score(x),
                x["key"],
            )
        )

    diversity = []
    while any(buckets.values()):
        for rid in sorted(buckets):
            if buckets[rid]:
                diversity.append(buckets[rid].pop(0))

    # Interleave selection modes across the entire queue.
    orders = {
        "exploit": exploitation,
        "explore": exploration,
        "diverse": diversity,
    }
    offsets = {name: 0 for name in orders}
    schedule = (
        ["exploit"] * 5
        + ["explore"] * 3
        + ["diverse"] * 2
    )

    selected = []
    seen = set()

    while len(selected) < len(remaining):
        progressed = False

        for mode in schedule:
            rows = orders[mode]
            index = offsets[mode]

            while index < len(rows) and rows[index]["key"] in seen:
                index += 1

            offsets[mode] = index + 1

            if index >= len(rows):
                continue

            candidate = rows[index]
            seen.add(candidate["key"])


            assessment = assess(candidate)

            selected.append({
                "key": candidate["key"],
                "mode": mode,
                "predictedScore": round(
                    assessment["priority"], 6
                ),
                "predictedUtility": round(
                    assessment["utility"], 6
                ),
                "predictedFeasibility": assessment[
                    "feasibility"
                ],
                "predictedViolations": assessment[
                    "violations"
                ],
                "removalObservations": assessment[
                    "removalObservations"
                ],
            })

            progressed = True

        if not progressed:
            break

    if len(selected) != len(remaining):
        raise RuntimeError("Queue did not cover all remaining pairs")

    if xml_sha256(xml_path) != digest:
        raise RuntimeError("XML changed during planning")

    output = directory / "adaptive_queue.json"
    payload = {
        "version": "0.6",
        "xmlPath": str(xml_path),
        "xmlSha256": digest,
        "skillGroup": SKILL_GROUP,
        "historicalCount": len(completed),
        "remainingCount": len(remaining),
        "queue": selected,
    }

    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=== ADAPTIVE QUEUE v0.6 ===")
    print("Historical:", len(completed))
    print("Remaining:", len(remaining))
    print("Removal effects estimated:", len(effects))
    print("Queue size:", len(selected))
    print("First 10:")
    for row in selected[:10]:
        print(
            row["mode"],
            row["key"],
            "score:", row["predictedScore"],
        )
    print("Saved:", output)


if __name__ == "__main__":
    main()
