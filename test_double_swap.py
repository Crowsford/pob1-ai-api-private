
import os

from experiment_runner import evaluate
from build_validator import validate_experiment
from build_constraints import evaluate_constraints

xml_path = os.environ["BUILD_XML"]

baseline = evaluate(xml_path, skill_group=6)

result = evaluate(
    xml_path,
    nodes=[63138, 55571],
    remove_nodes=[22315, 47085],
    skill_group=6,
)

print("=== DOUBLE SWAP VALIDATION ===")

removed = [
    n["nodeId"]
    for n in result["removalExperiment"]["nodes"]
]

added = [
    n["nodeId"]
    for n in result["passiveExperiment"]["nodes"]
]

print("Removed nodes:", removed)
print("Added nodes:", added)

assert sorted(removed) == [22315, 47085]
assert sorted(added) == [55571, 63138]

assert (
    result["passivePointsUsed"]
    == baseline["passivePointsUsed"]
), "Passive point count changed"

validation = validate_experiment(baseline, result)

row = {
    "removeId": -1,
    "removeName": "Double removal",
    "addId": -1,
    "addName": "Double addition",
    "stats": result["stats"],
    "validation": validation,
}

constraints = evaluate_constraints(baseline, row)

print("Base validation:", validation["status"])
print("Constraints:", constraints["status"])
print("Problems:", constraints["problems"])

print("\n=== STAT CHANGES ===")

keys = [
    "combinedDPS",
    "totalEHP",
    "energyShield",
    "blockChance",
    "spellBlockChance",
    "energyShieldRecharge",
    "manaUnreserved",
    "manaRegen",
]

for key in keys:
    before = baseline["stats"][key]
    after = result["stats"][key]
    print(
        f"{key}: {before:.2f} -> {after:.2f} "
        f"({after - before:+.2f})"
    )

print("\nPassive points:", result["passivePointsUsed"])
