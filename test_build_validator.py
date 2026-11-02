
import json
import os

from experiment_runner import evaluate
from build_validator import validate_experiment

xml_path = os.environ["BUILD_XML"]

print("[1/2] Baseline")
baseline = evaluate(xml_path)

print("[2/2] Replacement 5296 -> 50082")
modified = evaluate(
    xml_path,
    nodes=[50082],
    remove_nodes=[5296],
)

report = validate_experiment(baseline, modified)

print(json.dumps(report, indent=2))
