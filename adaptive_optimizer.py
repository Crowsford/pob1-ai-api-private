
# PoE BuildLab AI — Adaptive Optimizer v0.6
# Deterministic candidate selection, resumable PoB evaluation.

import itertools
import os
from pathlib import Path

from experiment_runner import evaluate
from experiment_storage import (
    get_experiment_dir,
    load_report,
    save_report,
    xml_sha256,
)
from build_validator import validate_experiment
from build_constraints import evaluate_constraints
from recovery_search import parse_tree_conflict

SKILL_GROUP = 6
MAX_EXPERIMENTS = 40
EXPLOIT_COUNT = 20

# Observed DPS prediction bias for combinations containing
# removal 9392 and addition 55571.
# Provisional: must be validated on unseen experiments.
AURA_CORRECTION = -0.33516


def make_key(removes, adds):
    return (
        ",".join(map(str, removes))
        + "->"
        + ",".join(map(str, adds))
    )


def main():
    xml_path = Path(os.environ["BUILD_XML"]).resolve()
    xml_hash = xml_sha256(xml_path)
    directory = get_experiment_dir(xml_path, SKILL_GROUP)

    singles = load_report(
        directory / "swap_constrained.json",
        xml_path, SKILL_GROUP,
    )
    executed = load_report(
        directory / "swap_executed.json",
        xml_path, SKILL_GROUP,
    )
    multi = load_report(
        directory / "multi_swap_results.json",
        xml_path, SKILL_GROUP,
    )
    recovery = load_report(
        directory / "recovery_results.json",
        xml_path, SKILL_GROUP,
    )

    if not multi["complete"] or not recovery["complete"]:
        raise RuntimeError("Previous experiments are incomplete")

    matrix = {
        (int(r["removeId"]), int(r["addId"])): r["changes"]
        for r in singles["results"]
    }

    if len(matrix) != len(singles["results"]):
        raise RuntimeError("Duplicate single-swap records")

    removals = sorted({r for r, _ in matrix})
    additions = sorted({a for _, a in matrix})

    previously_checked = {
        c["key"] for c in multi["candidates"]
    } | {
        c["key"] for c in recovery["candidates"]
    }

    candidates = []

    for rs in itertools.combinations(removals, 2):
        for ads in itertools.combinations(additions, 2):
            if set(rs) & set(ads):
                continue

            key = make_key(rs, ads)

            if key in previously_checked:
                continue

            def estimate(field):
                return sum(
                    matrix[r, a][field]
                    for r in rs
                    for a in ads
                ) / 2

            dps = estimate("dps_percent")
            ehp = estimate("ehp_percent")
            mana = estimate("free_mana_percent")
            recharge = estimate("es_recharge_percent")
            regen = estimate("mana_regen_percent")

            aura_pair = 9392 in rs and 55571 in ads

            if aura_pair:
                dps += AURA_CORRECTION

            predicted_pass = (
                dps >= 0
                and ehp >= 0
                and mana >= -10
                and recharge >= -5
                and regen >= -10
            )

            candidates.append({
                "key": key,
                "removeIds": list(rs),
                "addIds": list(ads),
                "predictedDps": dps,
                "predictedEhp": ehp,
                "predictedPass": predicted_pass,
                "predictedScore": (dps + ehp) / 2,
                "auraCorrectionApplied": aura_pair,
            })

    # Exploitation: best estimated candidates.
    ranked = sorted(
        candidates,
        key=lambda c: (
            not c["predictedPass"],
            -c["predictedScore"],
            c["key"],
        ),
    )

    exploit = ranked[:EXPLOIT_COUNT]
    selected_keys = {c["key"] for c in exploit}

    # Exploration: prioritize less-represented removal pairs
    # and addition pairs. No randomness, so the plan is
    # reproducible across restarts.
    pair_counts = {}

    for candidate in exploit:
        for kind in ("removeIds", "addIds"):
            pair = (kind, tuple(candidate[kind]))
            pair_counts[pair] = pair_counts.get(pair, 0) + 1

    explore = []
    remaining = [
        c for c in candidates
        if c["key"] not in selected_keys
    ]

    while len(exploit) + len(explore) < MAX_EXPERIMENTS and remaining:
        def exploration_priority(c):
            return (
                pair_counts.get(
                    ("removeIds", tuple(c["removeIds"])), 0
                )
                + pair_counts.get(
                    ("addIds", tuple(c["addIds"])), 0
                ),
                not c["predictedPass"],
                -c["predictedScore"],
                c["key"],
            )

        candidate = min(remaining, key=exploration_priority)
        remaining.remove(candidate)
        explore.append(candidate)

        for kind in ("removeIds", "addIds"):
            pair = (kind, tuple(candidate[kind]))
            pair_counts[pair] = pair_counts.get(pair, 0) + 1

    selected = exploit + explore
    output = directory / "adaptive_results.json"

    if output.exists():
        report = load_report(output, xml_path, SKILL_GROUP)

        if (
            report.get("version") != "0.6"
            or report.get("candidates") != selected
            or report.get("xmlSha256") != xml_hash
        ):
            raise RuntimeError("Saved adaptive plan mismatch")
    else:
        report = {
            "version": "0.6",
            "xmlPath": str(xml_path),
            "xmlSha256": xml_hash,
            "skillGroup": SKILL_GROUP,
            "available": len(candidates),
            "candidates": selected,
            "results": [],
            "invalidTrees": [],
            "errors": [],
            "complete": False,
        }
        save_report(output, report)

    processed_list = (
        [r["key"] for r in report["results"]]
        + [r["key"] for r in report["invalidTrees"]]
        + [r["key"] for r in report["errors"]]
    )

    if (
        len(processed_list) != len(set(processed_list))
        or not set(processed_list).issubset(
            {c["key"] for c in selected}
        )
    ):
        raise RuntimeError("Invalid saved results")

    processed = set(processed_list)
    baseline = executed["baseline"]

    print("=== ADAPTIVE OPTIMIZER v0.6 ===")
    print("Available unexplored:", len(candidates))
    print("Selected:", len(selected))
    print("Exploitation:", len(exploit))
    print("Exploration:", len(explore))
    print("Already processed:", len(processed))

    try:
        for i, candidate in enumerate(selected, 1):
            key = candidate["key"]

            if key in processed:
                continue

            if xml_sha256(xml_path) != xml_hash:
                raise RuntimeError("Source XML changed")

            print(f"[{i}/{len(selected)}] {key}", flush=True)

            try:
                result = evaluate(
                    xml_path,
                    nodes=candidate["addIds"],
                    remove_nodes=candidate["removeIds"],
                    skill_group=SKILL_GROUP,
                )

                actual_removes = sorted(
                    n["nodeId"]
                    for n in result["removalExperiment"]["nodes"]
                )
                actual_adds = sorted(
                    n["nodeId"]
                    for n in result["passiveExperiment"]["nodes"]
                )

                if (
                    actual_removes != candidate["removeIds"]
                    or actual_adds != candidate["addIds"]
                    or result["passivePointsUsed"]
                    != baseline["passivePointsUsed"]
                ):
                    raise RuntimeError("Experiment integrity failure")

                validation = validate_experiment(baseline, result)

                row = {
                    "removeId": ",".join(
                        map(str, candidate["removeIds"])
                    ),
                    "removeName": "Adaptive removal",
                    "addId": ",".join(
                        map(str, candidate["addIds"])
                    ),
                    "addName": "Adaptive addition",
                    "stats": result["stats"],
                    "validation": validation,
                }

                checked = evaluate_constraints(baseline, row)

                dps = checked["changes"]["dps_percent"]
                ehp = checked["changes"]["ehp_percent"]

                report["results"].append({
                    "key": key,
                    "status": checked["status"],
                    "problems": checked["problems"],
                    "changes": checked["changes"],
                    "stats": result["stats"],
                    "predictedDps": candidate["predictedDps"],
                    "predictedEhp": candidate["predictedEhp"],
                    "dpsError": dps - candidate["predictedDps"],
                    "ehpError": ehp - candidate["predictedEhp"],
                })

                print(
                    f"  {checked['status']}"
                    f" | DPS {dps:+.4f}%"
                    f" | EHP {ehp:+.4f}%",
                    flush=True,
                )

            except Exception as exc:
                conflict = parse_tree_conflict(str(exc))

                if conflict is not None:
                    report["invalidTrees"].append({
                        "key": key,
                        **conflict,
                    })
                    print(
                        "  INVALID_TREE",
                        conflict["disconnectedNodes"],
                        flush=True,
                    )
                else:
                    report["errors"].append({
                        "key": key,
                        "error": str(exc),
                    })
                    print("  ERROR:", exc, flush=True)

            if xml_sha256(xml_path) != xml_hash:
                raise RuntimeError("Source XML changed")

            save_report(output, report)
            processed.add(key)

    except KeyboardInterrupt:
        print("Interrupted. Saved completed experiments.")
        return

    report["complete"] = len(processed) == len(selected)
    save_report(output, report)

    passed = [
        r for r in report["results"]
        if r["status"] == "PASS"
    ]

    passed.sort(
        key=lambda r: (
            r["changes"]["dps_percent"]
            + r["changes"]["ehp_percent"]
        ),
        reverse=True,
    )

    print("\n=== ADAPTIVE RESULTS ===")
    print("Complete:", report["complete"])
    print("Calculated:", len(report["results"]))
    print("Passed:", len(passed))
    print("Invalid trees:", len(report["invalidTrees"]))
    print("Other errors:", len(report["errors"]))

    print("\nTOP 5:")
    for row in passed[:5]:
        changes = row["changes"]
        print(
            row["key"],
            f"DPS {changes['dps_percent']:+.4f}%",
            f"EHP {changes['ehp_percent']:+.4f}%",
            f"DPS error {row['dpsError']:+.4f} pp",
        )

    print("Saved:", output)


if __name__ == "__main__":
    main()
