
# PoE BuildLab — Swap Planner v0.1

import hashlib
import json
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ADD_FILE = ROOT / "candidate_scores_bababan99.json"
REMOVE_FILE = ROOT / "removal_scores_bababan99.json"
OUTPUT = ROOT / "swap_plan.json"

SKILL_GROUP = 6
MAX_REMOVALS = 6
MAX_ADDITIONS = 12


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Invalid numeric value: {value}")
    if not math.isfinite(value):
        raise ValueError(f"Non-finite value: {value}")
    return float(value)


def same_baseline(a, b):
    if a["level"] != b["level"]:
        return False
    if a["passivePointsUsed"] != b["passivePointsUsed"]:
        return False

    for key in (
        "combinedDPS",
        "totalEHP",
        "energyShield",
        "manaUnreserved",
    ):
        x = number(a["stats"][key])
        y = number(b["stats"][key])
        if not math.isclose(x, y, rel_tol=1e-8, abs_tol=1e-5):
            return False

    return True


def unique_by_id(groups, limit):
    result = []
    seen = set()

    for group in groups:
        for node in group:
            node_id = int(node["id"])
            if node_id not in seen:
                seen.add(node_id)
                result.append(node)
                if len(result) >= limit:
                    return result

    return result


def main():
    xml_raw = os.environ.get("BUILD_XML")
    if not xml_raw:
        raise RuntimeError("BUILD_XML is not set")

    xml_path = Path(xml_raw).resolve()
    if not xml_path.is_file():
        raise FileNotFoundError(xml_path)

    xml_hash = hashlib.sha256(xml_path.read_bytes()).hexdigest()

    additions_data = load(ADD_FILE)
    removals_data = load(REMOVE_FILE)

    add_base = additions_data["baseline"]
    remove_base = removals_data["baseline"]

    if additions_data.get("complete") is not True:
        raise RuntimeError("Addition scan is incomplete")

    if additions_data.get("errors"):
        raise RuntimeError("Addition scan contains errors")

    if removals_data.get("errors"):
        raise RuntimeError("Removal scan contains errors")

    if additions_data.get("skillGroup") != SKILL_GROUP:
        raise RuntimeError("Wrong skill group in addition results")

    if removals_data.get("skillGroup") != SKILL_GROUP:
        raise RuntimeError("Wrong skill group in removal results")

    if not same_baseline(add_base, remove_base):
        raise RuntimeError("Baseline mismatch between score files")

    for data in (additions_data, removals_data):
        saved_path = Path(data["xmlPath"]).resolve()
        if saved_path != xml_path:
            raise RuntimeError(
                f"XML path mismatch: {saved_path}"
            )

    adds = additions_data["scores"]
    removes = removals_data["results"]

    if len(adds) != additions_data["candidateCount"]:
        raise RuntimeError("Incomplete addition scores")

    if len(removes) != removals_data["calculated"]:
        raise RuntimeError("Incomplete removal scores")

    # Select candidates across multiple objectives.
    best_dps = sorted(
        adds,
        key=lambda n: number(n["dpsGain"]),
        reverse=True,
    )
    best_ehp = sorted(
        adds,
        key=lambda n: number(n["ehpGain"]),
        reverse=True,
    )
    best_regen = sorted(
        adds,
        key=lambda n: number(n["esRegenGain"]),
        reverse=True,
    )

    selected_adds = unique_by_id(
        [best_dps[:6], best_ehp[:6], best_regen[:6]],
        MAX_ADDITIONS,
    )

    least_dps_loss = sorted(
        removes,
        key=lambda n: number(n["dpsChange"]),
        reverse=True,
    )
    least_ehp_loss = sorted(
        removes,
        key=lambda n: number(n["ehpChange"]),
        reverse=True,
    )
    least_regen_loss = sorted(
        removes,
        key=lambda n: number(n["esRegenChange"]),
        reverse=True,
    )

    selected_removes = unique_by_id(
        [
            least_dps_loss[:4],
            least_ehp_loss[:4],
            least_regen_loss[:4],
        ],
        MAX_REMOVALS,
    )

    pairs = []

    for remove in selected_removes:
        for add in selected_adds:
            remove_id = int(remove["id"])
            add_id = int(add["id"])

            if remove_id == add_id:
                continue

            # Estimated effect for prioritization only.
            # Actual swaps MUST be recalculated by PoB.
            estimated_dps = (
                number(add["dpsGain"])
                + number(remove["dpsChange"])
            )
            estimated_ehp = (
                number(add["ehpGain"])
                + number(remove["ehpChange"])
            )

            pairs.append({
                "removeId": remove_id,
                "removeName": remove["name"],
                "addId": add_id,
                "addName": add["name"],
                "estimatedDpsChange": estimated_dps,
                "estimatedEhpChange": estimated_ehp,
                "status": "NOT_EVALUATED",
            })

    pairs.sort(
        key=lambda p: (
            -p["estimatedDpsChange"],
            -p["estimatedEhpChange"],
        )
    )

    report = {
        "version": "0.1",
        "xmlPath": str(xml_path),
        "xmlSha256": xml_hash,
        "sourceHashesVerified": False,
        "sourceBaselineMatch": True,
        "skillGroup": SKILL_GROUP,
        "selectedRemovals": len(selected_removes),
        "selectedAdditions": len(selected_adds),
        "plannedPairs": len(pairs),
        "pairs": pairs,
    }

    OUTPUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=== SWAP PLAN ===")
    print("XML SHA-256:", xml_hash)
    print("Source baselines consistent: YES")
    print("Source hashes verified: NO (legacy reports)")
    print("Skill group:", SKILL_GROUP)
    print("Removal candidates:", len(selected_removes))
    print("Addition candidates:", len(selected_adds))
    print("Planned pairs:", len(pairs))

    print("\n=== TOP 10 ESTIMATED ===")
    for pair in pairs[:10]:
        print(
            f"{pair['removeId']} -> {pair['addId']}: "
            f"Estimated DPS {pair['estimatedDpsChange']:+.2f}, "
            f"EHP {pair['estimatedEhpChange']:+.2f}"
        )

    print("\nSaved:", OUTPUT.name)
    print("These estimates are not PoB swap results.")


if __name__ == "__main__":
    main()
