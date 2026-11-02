import json
import os
from experiment_runner import evaluate

xml_path = os.environ.get("BUILD_XML")

if not xml_path:
    raise RuntimeError("BUILD_XML is not set")

result = evaluate(
    xml_path,
    nodes=[50082],
    remove_nodes=[5296],
)

print("OK:", result["ok"])
print("Removed:", result["removalExperiment"]["nodes"])
print("Added:", result["passiveExperiment"]["nodes"])
print("Points:", result["passivePointsUsed"])
print("DPS:", result["stats"]["combinedDPS"])
print("EHP:", result["stats"]["totalEHP"])
baseline = evaluate(xml_path)

print("\n=== BASELINE VALIDATION ===")
print(json.dumps(baseline["validation"], indent=2))

print("\n=== REPLACEMENT VALIDATION ===")
print(json.dumps(result["validation"], indent=2))
print("\n=== RESOURCE COSTS ===")
for name, data in [("BASELINE", baseline), ("REPLACEMENT", result)]:
    s = data["stats"]
    print(name, {
        "manaCost": s.get("manaCost"),
        "manaPerSecond": s.get("manaPerSecond"),
        "lifeCost": s.get("lifeCost"),
        "manaUnreserved": s.get("manaUnreserved"),
        "manaRegen": s.get("manaRegen"),
    })