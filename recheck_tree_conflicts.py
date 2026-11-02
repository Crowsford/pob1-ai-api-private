
import os

from experiment_runner import evaluate
from experiment_storage import (
    get_experiment_dir,
    load_report,
    save_report,
)
from recovery_search import parse_tree_conflict

xml_path = os.environ["BUILD_XML"]
directory = get_experiment_dir(xml_path, 6)
output = directory / "recovery_results.json"

report = load_report(output, xml_path, 6)

if report.get("version") != "0.5.1":
    raise RuntimeError("Expected recovery report v0.5.1")

candidates = {
    candidate["key"]: candidate
    for candidate in report["candidates"]
}

old_errors = list(report["errors"])

print("=== TREE CONFLICT RECHECK ===")
print("Errors to recheck:", len(old_errors))

for entry in old_errors:
    key = entry["key"]
    candidate = candidates[key]

    print("Checking:", key, flush=True)

    try:
        evaluate(
            xml_path,
            nodes=candidate["addIds"],
            remove_nodes=candidate["removeIds"],
            skill_group=6,
        )
    except RuntimeError as exc:
        conflict = parse_tree_conflict(str(exc))

        if conflict is None:
            print("  Other error:", str(exc)[:200])
            continue

        report["invalidTrees"].append({
            "key": key,
            **conflict,
        })

        report["errors"] = [
            error
            for error in report["errors"]
            if error["key"] != key
        ]

        save_report(output, report)

        print(
            "  INVALID_TREE",
            "Requested:", conflict["requestedNode"],
            "Disconnected:", conflict["disconnectedNodes"],
        )
    else:
        print("  WARNING: Previously failing combination succeeded")

processed = (
    [row["key"] for row in report["results"]]
    + [row["key"] for row in report["invalidTrees"]]
    + [row["key"] for row in report["errors"]]
)

expected = {row["key"] for row in report["candidates"]}

if len(processed) != len(set(processed)) or set(processed) != expected:
    raise RuntimeError("Report integrity check failed")

print("\n=== RECHECK RESULTS ===")
print("Calculated:", len(report["results"]))
print("Invalid trees:", len(report["invalidTrees"]))
print("Other errors:", len(report["errors"]))
print("Total processed:", len(processed))
