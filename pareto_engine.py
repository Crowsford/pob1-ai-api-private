
# PoE BuildLab AI — Pareto Engine v1.1
# Analysis only: never invokes PoB or changes the build.

import math
import os
from collections import defaultdict
from pathlib import Path

from experiment_storage import (
    get_experiment_dir,
    load_report,
    save_report,
    xml_sha256,
)

SKILL_GROUP = 6
VERSION = "1.1"

REPORTS = (
    "multi_swap_results.json",
    "recovery_results.json",
    "adaptive_results.json",
    "multi_swap_executed_v08.json",
    "multi_swap_executed_v09.json",
    "multi_swap_executed_v10.json",
    "multi_swap_executed_v11.json",
)

METRICS = (
    "dps_percent",
    "ehp_percent",
    "mana_regen_percent",
)

EPS = 1e-7


def metrics_of(row):
    changes = row["changes"]
    values = tuple(float(changes[k]) for k in METRICS)

    if not all(math.isfinite(v) for v in values):
        raise ValueError(
            f"Invalid metrics for {row.get('key')}"
        )

    return values


def dominates(a, b):
    """True if a is no worse in all metrics
    and materially better in at least one.
    """
    return (
        all(x >= y - EPS for x, y in zip(a, b))
        and any(x > y + EPS for x, y in zip(a, b))
    )


def assess_candidate(values, frontier):
    """Compare a predicted or measured point to the
    established Pareto frontier.

    This function does not validate the passive tree
    or check build constraints.
    """
    if isinstance(values, dict):
        values = metrics_of({"changes": values})

    values = tuple(float(v) for v in values)

    if len(values) != len(METRICS):
        raise ValueError("Invalid metric count")

    if not all(math.isfinite(v) for v in values):
        raise ValueError("Non-finite candidate metrics")

    frontier_values = [
        metrics_of(row) for row in frontier
    ]

    dominated_by = sum(
        dominates(existing, values)
        for existing in frontier_values
    )

    dominates_count = sum(
        dominates(values, existing)
        for existing in frontier_values
    )

    equivalent_count = sum(
        all(abs(a - b) <= EPS for a, b in zip(values, existing))
        for existing in frontier_values
    )

    return {
        "isDominated": dominated_by > 0,
        "dominatedByCount": dominated_by,
        "dominatesFrontierCount": dominates_count,
        "equivalentFrontierCount": equivalent_count,
        "isParetoCandidate": dominated_by == 0,
    }


def load_history(directory, xml_path):
    rows = []
    seen = set()
    counts = {}

    for filename in REPORTS + ("multi_swap_executed_v12.json",):
        report = load_report(
            directory / filename,
            xml_path,
            SKILL_GROUP,
        )

        if report.get("errors"):
            raise RuntimeError(
                f"Unresolved errors in {filename}"
            )

        source_rows = report.get("results", [])
        counts[filename] = {
            "calculated": len(source_rows),
            "pass": 0,
            "reject": 0,
        }

        for row in source_rows:
            key = row["key"]

            if key in seen:
                raise RuntimeError(
                    f"Duplicate experiment: {key}"
                )

            seen.add(key)

            status = row["status"]

            if status == "PASS":
                metrics_of(row)
                counts[filename]["pass"] += 1

                rows.append({
                    "key": key,
                    "source": filename,
                    "changes": row["changes"],
                    "stats": row["stats"],
                })

            elif status == "REJECT":
                counts[filename]["reject"] += 1

            else:
                raise RuntimeError(
                    f"Unknown status: {status}"
                )

    return rows, counts


def build_frontier(rows):
    """Retain every nondominated topology,
    including equivalent metric points.
    """
    points = [(row, metrics_of(row)) for row in rows]

    result = []

    for row, values in points:
        if not any(
            dominates(other_values, values)
            for other, other_values in points
            if other is not row
        ):
            result.append(row)

    return sorted(
        result,
        key=lambda row: (
            -metrics_of(row)[0],
            -metrics_of(row)[1],
            -metrics_of(row)[2],
            row["key"],
        ),
    )


def group_frontier(frontier):
    """Group measured points for reporting only.

    Different node combinations are NEVER discarded.
    """
    groups = defaultdict(list)

    for row in frontier:
        signature = tuple(
            round(v, 6) for v in metrics_of(row)
        )
        groups[signature].append(row["key"])

    return [
        {
            "metrics": dict(zip(METRICS, signature)),
            "combinations": keys,
            "topologyCount": len(keys),
        }
        for signature, keys in groups.items()
    ]


def main():
    raw = os.environ.get("BUILD_XML")
    if not raw:
        raise RuntimeError("BUILD_XML is not set")

    xml_path = Path(raw).resolve()
    digest = xml_sha256(xml_path)
    directory = get_experiment_dir(
        xml_path, SKILL_GROUP
    )

    rows, counts = load_history(directory, xml_path)
    frontier = build_frontier(rows)
    groups = group_frontier(frontier)

    if xml_sha256(xml_path) != digest:
        raise RuntimeError("Build XML changed")

    report = {
        "version": VERSION,
        "xmlPath": str(xml_path),
        "xmlSha256": digest,
        "skillGroup": SKILL_GROUP,
        "metrics": list(METRICS),
        "sourceCounts": counts,
        "totalPass": len(rows),
        "frontierCombinations": len(frontier),
        "uniqueMetricPoints": len(groups),
        "frontier": frontier,
        "groups": groups,
    }

    output = directory / "pareto_frontier.json"
    save_report(output, report)

    print("=== PARETO ENGINE v1.1 ===")
    print("Total PASS:", len(rows))
    print("Frontier combinations:", len(frontier))
    print("Unique metric points:", len(groups))
    print()

    for row in frontier:
        dps, ehp, mana = metrics_of(row)

        print(
            row["key"],
            "DPS:", round(dps, 4),
            "EHP:", round(ehp, 4),
            "Mana:", round(mana, 4),
        )

    print()
    print("Saved:", output)


if __name__ == "__main__":
    main()
