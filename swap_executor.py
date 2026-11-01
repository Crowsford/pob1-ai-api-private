
# PoE BuildLab — Swap Executor v0.1

import hashlib
import json
import os
import sys
from pathlib import Path

from experiment_runner import evaluate
from build_validator import validate_experiment

ROOT = Path(__file__).resolve().parent
PLAN_FILE = ROOT / "swap_plan.json"
OUTPUT_FILE = ROOT / "swap_executed.json"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(report):
    OUTPUT_FILE.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main():
    xml_raw = os.environ.get("BUILD_XML")
    if not xml_raw:
        raise RuntimeError("BUILD_XML is not set")

    xml_path = Path(xml_raw).resolve()
    plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))

    if xml_path != Path(plan["xmlPath"]).resolve():
        raise RuntimeError("Plan XML path does not match BUILD_XML")

    xml_hash = sha256(xml_path)

    if xml_hash != plan["xmlSha256"]:
        raise RuntimeError(
            "Build XML changed since planning. "
            "Rebuild the swap plan."
        )

    if plan.get("sourceHashesVerified") is not True:
        print(
            "WARNING: Legacy source score hashes were not verified.",
            flush=True,
        )

    if len(plan["pairs"]) != plan["plannedPairs"]:
        raise RuntimeError("Incomplete swap plan")

    skill_group = plan["skillGroup"]

    print("[Baseline] Evaluating original build", flush=True)
    baseline = evaluate(xml_path, skill_group=skill_group)

    if baseline["stats"]["combinedDPS"] <= 0:
        raise RuntimeError("Invalid main skill DPS")

    report = {
        "version": "0.1",
        "xmlPath": str(xml_path),
        "xmlSha256": xml_hash,
        "skillGroup": skill_group,
        "sourceHashesVerified": plan.get(
            "sourceHashesVerified", False
        ),
        "baseline": baseline,
        "planned": len(plan["pairs"]),
        "results": [],
        "rejected": [],
        "complete": False,
    }

    save(report)

    try:
        for index, pair in enumerate(plan["pairs"], 1):
            remove_id = pair["removeId"]
            add_id = pair["addId"]

            print(
                f"[{index}/{len(plan['pairs'])}] "
                f"{remove_id} -> {add_id}",
                flush=True,
            )

            try:
                result = evaluate(
                    xml_path,
                    nodes=[add_id],
                    remove_nodes=[remove_id],
                    skill_group=skill_group,
                )

                removed = result["removalExperiment"]["nodes"]
                added = result["passiveExperiment"]["nodes"]

                if [n["nodeId"] for n in removed] != [remove_id]:
                    raise ValueError("Unexpected removed node")

                if [n["nodeId"] for n in added] != [add_id]:
                    raise ValueError("Unexpected added node")

                if (
                    result["passivePointsUsed"]
                    != baseline["passivePointsUsed"]
                ):
                    raise ValueError("Passive point count changed")

                validation = validate_experiment(
                    baseline, result
                )

                old = baseline["stats"]
                new = result["stats"]

                report["results"].append({
                    "removeId": remove_id,
                    "removeName": pair["removeName"],
                    "addId": add_id,
                    "addName": pair["addName"],
                    "estimatedDpsChange": pair[
                        "estimatedDpsChange"
                    ],
                    "actualDpsChange": (
                        new["combinedDPS"]
                        - old["combinedDPS"]
                    ),
                    "dpsGainPercent": round(
                        100 * (
                            new["combinedDPS"]
                            / old["combinedDPS"] - 1
                        ),
                        4,
                    ),
                    "ehpChange": (
                        new["totalEHP"]
                        - old["totalEHP"]
                    ),
                    "stats": new,
                    "validation": validation,
                })

            except Exception as exc:
                print(f"  REJECTED: {exc}", flush=True)
                report["rejected"].append({
                    "removeId": remove_id,
                    "addId": add_id,
                    "error": str(exc),
                })

            save(report)

    except KeyboardInterrupt:
        print("\nInterrupted. Partial results saved.")
        return 130

    if sha256(xml_path) != xml_hash:
        raise RuntimeError(
            "XML changed during the experiment. "
            "Results must not be trusted."
        )

    report["complete"] = True
    save(report)

    ranked = sorted(
        report["results"],
        key=lambda row: row["actualDpsChange"],
        reverse=True,
    )

    print("\n=== TOP 10 ACTUAL SWAPS ===")

    for row in ranked[:10]:
        print(
            f"{row['removeId']} -> {row['addId']}: "
            f"DPS {row['dpsGainPercent']:+.4f}%, "
            f"EHP {row['ehpChange']:+.2f}, "
            f"Validation {row['validation']['status']}"
        )

    print(
        f"\nCalculated: {len(report['results'])} / "
        f"{report['planned']}"
    )
    print(f"Rejected: {len(report['rejected'])}")
    print("Saved:", OUTPUT_FILE.name)

    return 0


if __name__ == "__main__":
    sys.exit(main())
