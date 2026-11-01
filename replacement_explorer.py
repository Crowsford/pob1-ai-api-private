
# PoE BuildLab — Replacement Explorer v0.1

import json
import os
import sys

from experiment_runner import evaluate
from build_validator import validate_experiment

REMOVE_CANDIDATES = [5296, 9392, 21974, 25831]
ADD_CANDIDATE = 50082


def main():
    xml_path = os.environ.get("BUILD_XML")

    if not xml_path:
        raise RuntimeError("BUILD_XML environment variable is missing")

    print("[Baseline] Evaluating original build", flush=True)
    baseline = evaluate(xml_path)

    base_dps = baseline["stats"]["combinedDPS"]
    base_ehp = baseline["stats"]["totalEHP"]
    base_points = baseline["passivePointsUsed"]

    results = []

    for index, remove_id in enumerate(REMOVE_CANDIDATES, 1):
        print(
            f"[{index}/{len(REMOVE_CANDIDATES)}] "
            f"Remove {remove_id}, add {ADD_CANDIDATE}",
            flush=True,
        )

        try:
            result = evaluate(
                xml_path,
                nodes=[ADD_CANDIDATE],
                remove_nodes=[remove_id],
            )

            removed = result["removalExperiment"]["nodes"]
            added = result["passiveExperiment"]["nodes"]

            if result["passivePointsUsed"] != base_points:
                raise ValueError("Passive point count changed")

            if [n["nodeId"] for n in removed] != [remove_id]:
                raise ValueError("Unexpected removed nodes")

            if [n["nodeId"] for n in added] != [ADD_CANDIDATE]:
                raise ValueError("Unexpected added nodes")

            dps = result["stats"]["combinedDPS"]
            ehp = result["stats"]["totalEHP"]
            validation = validate_experiment(baseline, result)
            mana_cost = result["stats"].get("manaCost")
            mana_available = result["stats"].get("manaUnreserved")

            if mana_cost is None or mana_available is None:
                resource_status = "UNKNOWN"
            elif mana_cost <= mana_available:
                resource_status = "PASS"
            else:
                resource_status = "FAIL"

            mana_regen = result["stats"].get("manaRegen")
            cast_speed = result["stats"].get("speed")

            if (
                mana_cost is None
                or mana_regen is None
                or cast_speed is None
            ):
                sustain_status = "UNKNOWN"
                mana_per_second = None
            else:
                mana_per_second = mana_cost * cast_speed
                sustain_status = (
                    "PASS"
                    if mana_regen >= mana_per_second
                    else "FAIL"
                )

            results.append({
                "removeId": remove_id,
                "removeName": removed[0]["nodeName"],
                "addId": ADD_CANDIDATE,
                "addName": added[0]["nodeName"],
                "dps": dps,
                "dpsGain": dps - base_dps,
                "dpsGainPercent": round(
                    (dps / base_dps - 1) * 100, 4
                ),
                "ehp": ehp,
                "ehpChange": ehp - base_ehp,
                "energyShield": result["stats"]["energyShield"],
                "manaUnreserved": result["stats"]["manaUnreserved"],
                "validation": validation,
                "manaCost": mana_cost,
                "resourceStatus": resource_status,
                "fullSpamManaPerSecond": mana_per_second,
                "fullSpamSustainStatus": sustain_status,
                "practicalSustainStatus": "UNKNOWN",
                "ok": True,
            })

        except Exception as exc:
            print(f"  FAILED: {exc}", flush=True)
            results.append({
                "removeId": remove_id,
                "addId": ADD_CANDIDATE,
                "ok": False,
                "error": str(exc),
            })

    successful = [r for r in results if r["ok"]]
    successful.sort(
        key=lambda r: (
            r["validation"]["attributeRegression"]["status"] != "NO_REGRESSION",
            r["validation"]["budget"]["status"] != "VALID",
            -r["dpsGain"],
            -r["ehp"],
        )
    )

    report = {
        "baseline": {
            "combinedDPS": base_dps,
            "totalEHP": base_ehp,
            "passivePointsUsed": base_points,
        },
        "tested": len(results),
        "successful": len(successful),
        "ranked": successful,
        "failed": [r for r in results if not r["ok"]],
    }

    with open(
        "replacement_results.json", "w", encoding="utf-8"
    ) as file:
        json.dump(report, file, indent=2, ensure_ascii=False)

    print("\n=== RANKING ===")
    for item in successful:
        print(
            f"Remove {item['removeId']} "
            f"({item['removeName']}): "
            f"DPS {item['dpsGainPercent']:+.4f}%, "
            f"EHP {item['ehpChange']:+.2f}, "
            f"Mana unreserved {item['manaUnreserved']}, "
            f"Validation {item['validation']['status']}, "
            f"Regression {item['validation']['attributeRegression']['status']}, "
            f"Mana cost {item['manaCost']}, "
            f"Resource {item['resourceStatus']}"
            f", Full spam mana/s {item['fullSpamManaPerSecond']}"
            f", Full spam {item['fullSpamSustainStatus']}"
            f", Practical sustain {item['practicalSustainStatus']}"
        )

    print("\nSaved: replacement_results.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
