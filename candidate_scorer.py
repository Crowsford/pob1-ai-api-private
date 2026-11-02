
# PoE BuildLab — Candidate Scorer v0.1

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from experiment_runner import evaluate

from experiment_storage import (
    get_experiment_dir,
    metadata,
    save_report,
    xml_sha256,
)

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
OUTPUT = None

SKILL_GROUP = 6
PREFIX = "RESULT_JSON:"


def discover(xml_path):
    luajit = shutil.which("luajit")
    if not luajit:
        raise RuntimeError("LuaJIT not found")

    process = subprocess.run(
        [
            luajit,
            str(SRC / "passive_candidates.lua"),
            str(xml_path),
        ],
        cwd=SRC,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
    )

    if process.returncode != 0:
        raise RuntimeError(process.stdout + process.stderr)

    for line in process.stdout.splitlines():
        if line.startswith(PREFIX):
            return json.loads(line[len(PREFIX):])

    raise RuntimeError("Candidate discovery returned no JSON")


def save(report):
    save_report(OUTPUT, report)


def main():
    xml_path = os.environ.get("BUILD_XML")
    if not xml_path:
        raise RuntimeError("BUILD_XML is not set")

    xml_path = str(Path(xml_path).resolve())
    global OUTPUT

    OUTPUT = (
        get_experiment_dir(xml_path, SKILL_GROUP)
        / "candidate_scores.json"
    )

    source_hash = xml_sha256(xml_path)

    print("[Baseline] Evaluating Bane of Condemnation", flush=True)
    baseline = evaluate(xml_path, skill_group=SKILL_GROUP)

    base = baseline["stats"]
    assert base["combinedDPS"] > 0, "Invalid main skill DPS"

    print("[Discovery] Loading candidate nodes", flush=True)
    discovered = discover(xml_path)
    candidates = discovered["candidates"]

    report = {
        "version": "0.1",
        "xmlPath": xml_path,
        "skillGroup": SKILL_GROUP,
        "baseline": baseline,
        "candidateCount": len(candidates),
        "scores": [],
        "errors": [],
        "complete": False,
        "xmlSha256": source_hash,
    }

    print(f"Scanning {len(candidates)} nodes", flush=True)

    try:
        for index, candidate in enumerate(candidates, 1):
            node_id = int(candidate["id"])

            print(
                f"[{index}/{len(candidates)}] "
                f"{node_id} — {candidate['name']}",
                flush=True,
            )

            try:
                result = evaluate(
                    xml_path,
                    nodes=[node_id],
                    skill_group=SKILL_GROUP,
                )

                stats = result["stats"]

                if result["passivePointsUsed"] != (
                    baseline["passivePointsUsed"] + 1
                ):
                    raise ValueError("Unexpected passive point cost")

                dps_gain = (
                    stats["combinedDPS"] - base["combinedDPS"]
                )

                ehp_gain = stats["totalEHP"] - base["totalEHP"]

                report["scores"].append({
                    "id": node_id,
                    "name": candidate["name"],
                    "dpsGain": dps_gain,
                    "dpsGainPercent": round(
                        100 * dps_gain / base["combinedDPS"], 4
                    ),
                    "ehpGain": ehp_gain,
                    "esGain": (
                        stats["energyShield"] -
                        base["energyShield"]
                    ),
                    "esRegenGain": (
                        stats["energyShieldRegen"] -
                        base["energyShieldRegen"]
                    ),
                    "manaUnreserved": stats["manaUnreserved"],
                    "stats": stats,
                })

            except Exception as exc:
                print(f"  FAILED: {exc}", flush=True)
                report["errors"].append({
                    "id": node_id,
                    "error": str(exc),
                })

            # Save after each experiment, including failures.
            save(report)

    except KeyboardInterrupt:
        print("\nInterrupted. Partial results saved.", flush=True)
        return 130

    if xml_sha256(xml_path) != source_hash:
        raise RuntimeError(
            "XML changed during candidate scan. "
            "Results are not trusted."
        )

    report["complete"] = True
    save(report)

    print("\n=== TOP 10 DPS ===")
    for node in sorted(
        report["scores"],
        key=lambda x: x["dpsGain"],
        reverse=True,
    )[:10]:
        print(
            f"{node['id']} {node['name']}: "
            f"DPS {node['dpsGainPercent']:+.4f}%, "
            f"EHP {node['ehpGain']:+.2f}"
        )

    print("\n=== TOP 10 EHP ===")
    for node in sorted(
        report["scores"],
        key=lambda x: x["ehpGain"],
        reverse=True,
    )[:10]:
        print(
            f"{node['id']} {node['name']}: "
            f"EHP {node['ehpGain']:+.2f}, "
            f"DPS {node['dpsGainPercent']:+.4f}%"
        )

    print(
        f"\nCompleted: {len(report['scores'])}/"
        f"{len(candidates)}"
    )
    print(f"Errors: {len(report['errors'])}")
    print(f"Saved: {OUTPUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
