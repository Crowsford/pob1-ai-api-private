
# PoE BuildLab — Removal Scorer v0.1

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from experiment_runner import evaluate
from build_validator import validate_experiment

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
OUTPUT = ROOT / "removal_scores_bababan99.json"
SKILL_GROUP = 6
PREFIX = "RESULT_JSON:"


def discover(xml_path):
    luajit = shutil.which("luajit")
    if not luajit:
        raise RuntimeError("LuaJIT not found in PATH")

    process = subprocess.run(
        [luajit, str(SRC / "passive_candidates.lua"), str(xml_path)],
        cwd=SRC,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
    )

    if process.returncode != 0:
        raise RuntimeError(process.stdout + process.stderr)

    lines = [
        line[len(PREFIX):]
        for line in process.stdout.splitlines()
        if line.startswith(PREFIX)
    ]

    if len(lines) != 1:
        raise RuntimeError("Candidate discovery JSON missing")

    result = json.loads(lines[0])

    if result.get("ok") is not True:
        raise RuntimeError("Candidate discovery failed")

    return result


def main():
    xml_path = os.environ.get("BUILD_XML")

    if not xml_path:
        raise RuntimeError("BUILD_XML is not set")

    xml_path = str(Path(xml_path).resolve())

    print("[Baseline] Evaluating Bane of Condemnation", flush=True)
    baseline = evaluate(xml_path, skill_group=SKILL_GROUP)
    base = baseline["stats"]

    print("[Discovery] Finding removable nodes", flush=True)
    discovered = discover(xml_path)
    candidates = discovered["removalCandidates"]

    results = []
    errors = []

    for index, candidate in enumerate(candidates, 1):
        node_id = int(candidate["id"])

        print(
            f"[{index}/{len(candidates)}] "
            f"Remove {node_id} — {candidate['name']}",
            flush=True,
        )

        try:
            modified = evaluate(
                xml_path,
                remove_nodes=[node_id],
                skill_group=SKILL_GROUP,
            )

            removal = modified.get("removalExperiment")

            if removal is None:
                raise ValueError("Removal experiment missing")

            removed_ids = [
                node["nodeId"] for node in removal["nodes"]
            ]

            if removed_ids != [node_id]:
                raise ValueError("Unexpected removed nodes")

            if modified["passivePointsUsed"] != (
                baseline["passivePointsUsed"] - 1
            ):
                raise ValueError("Unexpected passive point refund")

            stats = modified["stats"]
            validation = validate_experiment(baseline, modified)

            results.append({
                "id": node_id,
                "name": candidate["name"],
                "dpsChange": (
                    stats["combinedDPS"] - base["combinedDPS"]
                ),
                "dpsChangePercent": round(
                    100 * (
                        stats["combinedDPS"] - base["combinedDPS"]
                    ) / base["combinedDPS"],
                    4,
                ),
                "ehpChange": (
                    stats["totalEHP"] - base["totalEHP"]
                ),
                "esChange": (
                    stats["energyShield"] - base["energyShield"]
                ),
                "esRegenChange": (
                    stats["energyShieldRegen"]
                    - base["energyShieldRegen"]
                ),
                "manaUnreservedChange": (
                    stats["manaUnreserved"]
                    - base["manaUnreserved"]
                ),
                "stats": stats,
                "validation": validation,
            })

        except Exception as exc:
            print(f"  FAILED: {exc}", flush=True)
            errors.append({
                "id": node_id,
                "error": str(exc),
            })

    # Higher DPS remaining after removal is better.
    results.sort(
        key=lambda item: item["dpsChange"],
        reverse=True,
    )

    report = {
        "version": "0.1",
        "xmlPath": xml_path,
        "skillGroup": SKILL_GROUP,
        "baseline": baseline,
        "attempted": len(candidates),
        "calculated": len(results),
        "errors": errors,
        "results": results,
    }

    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n=== LEAST DPS LOSS ===")
    for item in results[:12]:
        print(
            f"{item['id']} {item['name']}: "
            f"DPS {item['dpsChangePercent']:+.4f}%, "
            f"EHP {item['ehpChange']:+.2f}, "
            f"ES regen {item['esRegenChange']:+.2f}, "
            f"Mana {item['manaUnreservedChange']:+.2f}, "
            f"Validation {item['validation']['status']}"
        )

    print(
        f"\nCompleted: {len(results)}/{len(candidates)}; "
        f"Errors: {len(errors)}"
    )
    print(f"Saved: {OUTPUT.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
