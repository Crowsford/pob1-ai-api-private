
# PoE BuildLab — Combination Explorer v0.2
# Reuses validated single-node results.

import argparse
import hashlib
import itertools
import json
import math
import sys
from pathlib import Path

from experiment_runner import evaluate

METRICS = (
    "combinedDPS",
    "speed",
    "totalEHP",
    "life",
    "energyShield",
    "mana",
)


def metric_value(stats, metric):
    value = stats.get(metric)
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"Invalid metric {metric}: {value}")
    return value


def validate_allocation(result, expected_ids):
    info = result.get("passiveExperiment")

    if not isinstance(info, dict):
        raise ValueError("Missing passiveExperiment")

    actual_ids = [
        item["nodeId"]
        for item in info.get("nodes", [])
    ]

    if actual_ids != expected_ids:
        raise ValueError(
            f"Expected nodes {expected_ids}, got {actual_ids}"
        )

    if info.get("pointsSpent") != len(expected_ids):
        raise ValueError("Unexpected passive point cost")


def load_single_cache(path, metric, base_value):
    data = json.loads(path.read_text(encoding="utf-8"))

    if data.get("experiment") != "passive_explorer_v0.1":
        raise ValueError("Unsupported cache format")

    if data.get("metric") != metric:
        raise ValueError(
            "Cache metric does not match requested metric"
        )

    if data.get("ok") is not True or data.get("failed") != 0:
        raise ValueError("Cache contains failed experiments")

    results = data.get("results")

    if not isinstance(results, list) or not results:
        raise ValueError("Cache has no results")

    if (
        data.get("evaluated") != len(results)
        or data.get("candidateCount") != len(results)
    ):
        raise ValueError("Cache is incomplete")

    singles = []
    seen = set()

    for item in results:
        node_id = item.get("nodeId")

        if type(node_id) is not int or node_id <= 0:
            raise ValueError("Invalid node ID in cache")

        if node_id in seen:
            raise ValueError("Duplicate node in cache")

        seen.add(node_id)

        if item.get("pointsSpent") != 1:
            raise ValueError("Unexpected cached point cost")

        change = item.get("changes", {}).get(metric)

        if not isinstance(change, dict):
            raise ValueError(f"Missing metric for node {node_id}")

        before = change.get("before")
        after = change.get("after")

        if type(before) not in (int, float):
            raise ValueError("Invalid cached baseline")

        if type(after) not in (int, float) or not math.isfinite(after):
            raise ValueError("Invalid cached result")

        if not math.isclose(
            before, base_value, rel_tol=1e-9, abs_tol=1e-6
        ):
            raise ValueError(
                f"Cached baseline mismatch for node {node_id}"
            )

        singles.append({
            "id": node_id,
            "name": item["name"],
            "value": after,
            "gain": after - base_value,
        })

    singles.sort(key=lambda x: (-x["gain"], x["id"]))

    return singles


def explore(xml_path, cache_path, shortlist_size, metric, mode="research"):
    print("[Baseline] Evaluating original build",
          file=sys.stderr, flush=True)

    baseline = evaluate(xml_path)
    base_value = metric_value(baseline["stats"], metric)

    level = baseline["level"]
    extra_points = baseline["extraPoints"]
    points_used = baseline["passivePointsUsed"]

    if type(extra_points) is not int or extra_points < 0:
        raise ValueError("Invalid ExtraPoints from PoB")

    if type(points_used) is not int or points_used < 0:
        raise ValueError("Invalid passivePointsUsed from PoB")

    # For now, strict validation supports characters
    # who have completed the campaign.
    if mode == "valid" and level < 67:
        raise ValueError(
            "Valid mode currently requires level >= 67"
        )

    max_points = min(level - 1 + 23 + extra_points,
                     99 + 23 + extra_points)

    available_points = max_points - points_used

    print(
        f"[Budget] Used: {points_used}, "
        f"Maximum: {max_points}, "
        f"Available: {available_points}, "
        f"Mode: {mode}",
        file=sys.stderr,
        flush=True,
    )


    print("[Cache] Loading saved single-node results",
          file=sys.stderr, flush=True)

    singles = load_single_cache(cache_path, metric, base_value)

    shortlisted = singles[:shortlist_size]

    pairs = []
    errors = []
    skipped = []

    combinations = list(
        itertools.combinations(shortlisted, 2)
    )

    for index, (first, second) in enumerate(combinations, 1):
        ids = [first["id"], second["id"]]

        print(
            f"[Pairs {index}/{len(combinations)}] "
            f"{ids[0]} + {ids[1]}",
            file=sys.stderr,
            flush=True,
        )

        if mode == "valid" and available_points < 2:
            skipped.append({
                "nodes": ids,
                "reason": "Insufficient passive points",
                "required": 2,
                "available": available_points,
            })
            continue

        try:
            result = evaluate(xml_path, nodes=ids)
            validate_allocation(result, ids)

            value = metric_value(result["stats"], metric)
            gain = value - base_value

            expected_gain = first["gain"] + second["gain"]
            interaction = gain - expected_gain

            pairs.append({
                "nodes": [
                    {"id": first["id"], "name": first["name"]},
                    {"id": second["id"], "name": second["name"]},
                ],
                "pointsSpent": 2,
                "value": round(value, 6),
                "gain": round(gain, 6),
                "gainPercent": (
                    round(gain / abs(base_value) * 100, 4)
                    if base_value != 0 else None
                ),
                "interaction": round(interaction, 6),
                "defense": {
                    key: result["stats"].get(key)
                    for key in (
                        "life",
                        "energyShield",
                        "totalEHP",
                        "fireResist",
                        "coldResist",
                        "lightningResist",
                        "chaosResist",
                    )
                },
            })

        except Exception as exc:
            errors.append({
                "nodes": ids,
                "error": str(exc),
            })
            print(
                f"  ERROR: {exc}",
                file=sys.stderr,
                flush=True,
            )

    pairs.sort(
        key=lambda x: (-x["gain"], x["nodes"][0]["id"])
    )

    source_hash = hashlib.sha256(
        xml_path.read_bytes()
    ).hexdigest()

    return {
        "ok": not errors,
        "experiment": "combination_explorer_v0.2",
        "metric": metric,
        "baseline": base_value,
        "sourceXmlSHA256": source_hash,
        "cacheFile": str(cache_path),
        "singlesReused": len(singles),
        "shortlistSize": len(shortlisted),
        "shortlist": shortlisted,
        "pairsAttempted": len(combinations),
        "pairsEvaluated": len(pairs),
        "pairsFailed": len(errors),
	"topPairs": pairs[:10],
	"allPairs": pairs,
        "errors": errors,
        "limitations": [
            "Legacy single-node cache has no source XML hash",
            "Cache provenance must be confirmed externally",
            "Only two-node combinations are tested",
            "Shortlist is based on individual metric gain",
            "Passive point availability is not fully validated",
            "Defensive metrics are recorded but not constrained",
        ],
        "mode": mode,
        "passiveBudget": {
            "level": level,
            "extraPoints": extra_points,
            "maximum": max_points,
            "used": points_used,
            "available": available_points,
        },
        "pairsSkipped": len(skipped),
        "skipped": skipped,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Explore passive pairs using saved results"
    )

    parser.add_argument("xml_path")
    parser.add_argument("--single-cache", required=True)
    parser.add_argument("--trust-cache", action="store_true")
    parser.add_argument("--shortlist", type=int, default=8)

    parser.add_argument(
        "--metric",
        choices=METRICS,
        default="combinedDPS",
    )

    parser.add_argument("--output")

    parser.add_argument(
        "--mode",
        choices=("research", "valid"),
        default="research",
    )

    args = parser.parse_args()

    if not 2 <= args.shortlist <= 20:
        parser.error("--shortlist must be between 2 and 20")

    if not args.trust_cache:
        parser.error(
            "Legacy cache has no source hash. "
            "Verify that it belongs to this XML, "
            "then explicitly pass --trust-cache."
        )

    xml_path = Path(args.xml_path).expanduser().resolve()
    cache_path = Path(args.single_cache).expanduser().resolve()

    if not xml_path.is_file():
        parser.error(f"Build XML not found: {xml_path}")

    if not cache_path.is_file():
        parser.error(f"Cache file not found: {cache_path}")

    try:
        result = explore(
            xml_path,
            cache_path,
            args.shortlist,
            args.metric,
            args.mode,
        )

        output = json.dumps(
            result, ensure_ascii=False, indent=2,
            allow_nan=False,
        )

        if args.output:
            Path(args.output).write_text(
                output + "\n",
                encoding="utf-8",
            )
            print(
                f"Saved: {args.output}",
                file=sys.stderr,
            )
        else:
            print(output)

        return 0 if result["ok"] else 1

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

