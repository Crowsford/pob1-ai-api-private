
import os
from experiment_runner import evaluate

xml_path = os.environ["BUILD_XML"]

print("[1/2] Main skill only", flush=True)
baseline = evaluate(xml_path, skill_group=6)

print("[2/2] Main skill and explicit level", flush=True)
rechecked = evaluate(xml_path, level=99, skill_group=6)

fields = ("combinedDPS", "totalDotDPS", "manaCost", "speed", "totalEHP")

for field in fields:
    before = baseline["stats"][field]
    after = rechecked["stats"][field]
    print(f"{field}: {before} -> {after}")
    assert abs(before - after) < 0.0001, f"Mismatch: {field}"

assert baseline["passivePointsUsed"] == rechecked["passivePointsUsed"]
assert baseline["passivePointsUsed"] == 122

print("PASS: Skill selection and level override are consistent")
