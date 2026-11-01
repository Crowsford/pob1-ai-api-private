
# PoE BuildLab — Swap Explorer v0.1

import json
import os
import shutil
import subprocess
from pathlib import Path

from experiment_runner import evaluate
from build_validator import validate_experiment

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
PREFIX = "RESULT_JSON:"

SKILL_GROUP = 6
MAX_REMOVALS = 5
MAX_ADDITIONS = 10


def discover_candidates(xml_path):
    luajit = shutil.which("luajit")
    if not luajit:
        raise RuntimeError("LuaJIT not found in PATH")

    command = [
        luajit,
        str(SRC / "passive_candidates.lua"),
        str(xml_path),
    ]

    process = subprocess.run(
        command,
        cwd=SRC,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
    )

    if process.returncode != 0:
        raise RuntimeError(process.stderr or process.stdout)

    lines = [
        line[len(PREFIX):]
        for line in process.stdout.splitlines()
        if line.startswith(PREFIX)
    ]

    if len(lines) != 1:
        raise RuntimeError("Candidate discovery JSON missing")

    data = json.loads(lines[0])

    if data.get("ok") is not True:
        raise RuntimeError("Candidate discovery failed")

    return data


def main():
    xml_path = os.environ.get("BUILD_XML")
    if not xml_path:
        raise RuntimeError("BUILD_XML is not set")

    print("[Baseline] Evaluating Bane of Condemnation", flush=True)
    baseline = evaluate(xml_path, skill_group=SKILL_GROUP)

    if baseline["stats"]["combinedDPS"] <= 0:
        raise RuntimeError("Invalid baseline DPS; check skill group")

    print("[Discovery] Finding passive candidates", flush=True)
    discovered = discover_candidates(xml_path)


    removal_scores = json.loads(
        (ROOT / "removal_scores_bababan99.json").read_text(
            encoding="utf-8"
        )
    )

    addition_scores = json.loads(
        (ROOT / "candidate_scores_bababan99.json").read_text(
            encoding="utf-8"
        )
    )

    # Preliminary shortlist: low DPS loss and high DPS/EHP gain.
    removals_by_id = {
        int(n["id"]): n
        for n in discovered["removalCandidates"]
    }
    additions_by_id = {
        int(n["id"]): n
        for n in discovered["candidates"]
    }

    remove_ids = [7503, 22315, 21974, 25831, 4432]
    add_ids = [
        48971, 57264, 50472, 55571,
        13322, 22473, 1822, 49515,
    ]

    assert removal_scores["calculated"] == 12
    assert addition_scores["complete"] is True
    assert addition_scores["candidateCount"] == 102

    assert all(n in removals_by_id for n in remove_ids)
    assert all(n in additions_by_id for n in add_ids)

    removals = [removals_by_id[n] for n in remove_ids]
    additions = [additions_by_id[n] for n in add_ids]


    print(
        f"Candidates: {len(removals)} removals x "
        f"{len(additions)} additions",
        flush=True,
    )

    results = []
    rejected = []

    total = len(removals) * len(additions)
    index = 0

    for removal in removals:
        for addition in additions:
            index += 1
            remove_id = int(removal["id"])
            add_id = int(addition["id"])

            print(
                f"[{index}/{total}] "
                f"Remove {remove_id}, add {add_id}",
                flush=True,
            )

            try:
                modified = evaluate(
                    xml_path,
                    nodes=[add_id],
                    remove_nodes=[remove_id],
                    skill_group=SKILL_GROUP,
                )

                if modified["passivePointsUsed"] != baseline["passivePointsUsed"]:
                    raise ValueError("Passive point count changed")

                removed_ids = [
                    n["nodeId"]
                    for n in modified["removalExperiment"]["nodes"]
                ]
                added_ids = [
                    n["nodeId"]
                    for n in modified["passiveExperiment"]["nodes"]
                ]

                if removed_ids != [remove_id] or added_ids != [add_id]:
                    raise ValueError("Unexpected tree modification")

                validation = validate_experiment(baseline, modified)

                old_stats = baseline["stats"]
                new_stats = modified["stats"]

                results.append({
                    "removeId": remove_id,
                    "removeName": removal["name"],
                    "addId": add_id,
                    "addName": addition["name"],
                    "dps": new_stats["combinedDPS"],
                    "dpsGain": (
                        new_stats["combinedDPS"] -
                        old_stats["combinedDPS"]
                    ),
                    "dpsGainPercent": round(
                        (
                            new_stats["combinedDPS"] /
                            old_stats["combinedDPS"] - 1
                        ) * 100, 4
                    ),
                    "ehp": new_stats["totalEHP"],
                    "ehpChange": (
                        new_stats["totalEHP"] -
                        old_stats["totalEHP"]
                    ),
                    "manaUnreserved": new_stats["manaUnreserved"],
		    "manaCost": new_stats.get("manaCost"),
		    "stats": new_stats,
		    "validation": validation,
                })

            except Exception as exc:
                print(f"  REJECTED: {exc}", flush=True)
                rejected.append({
                    "removeId": remove_id,
                    "addId": add_id,
                    "error": str(exc),
                })

    results.sort(key=lambda x: x["dpsGain"], reverse=True)

    eligible = [
        r for r in results
        if r["validation"]["status"] == "VALID"
        and r["validation"]["attributeRegression"]["status"]
        == "NO_REGRESSION"
    ]

    report = {
        "skillGroup": SKILL_GROUP,
        "baseline": baseline,
        "discoveredRemovals": discovered["removalCandidateCount"],
        "discoveredAdditions": discovered["candidateCount"],
        "attempted": total,
        "calculated": len(results),
        "eligibleByCurrentChecks": len(eligible),
        "rejected": rejected,
        "results": results,
    }

    output = ROOT / "swap_results_targeted.json"
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n=== TOP 10 BY DPS ===")
    for item in results[:10]:
        print(
            f"{item['removeId']} -> {item['addId']}: "
            f"DPS {item['dpsGainPercent']:+.4f}%, "
            f"EHP {item['ehpChange']:+.2f}, "
            f"Validation {item['validation']['status']}"
        )

    print(
        f"\nCalculated: {len(results)} / {total}; "
        f"Eligible by current checks: {len(eligible)}; "
        f"Rejected by engine: {len(rejected)}"
    )
    print("Saved: swap_results.json")


if __name__ == "__main__":
    main()
