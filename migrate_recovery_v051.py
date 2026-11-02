
import os

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

if report.get("version") not in ("0.5", "0.5.1"):
    raise RuntimeError("Unsupported report version")

if not report.get("complete"):
    raise RuntimeError("Recovery search is incomplete")

invalid = report.setdefault("invalidTrees", [])
remaining_errors = []
migrated = 0

for entry in report["errors"]:
    conflict = parse_tree_conflict(entry["error"])

    if conflict is None:
        remaining_errors.append(entry)
        continue

    invalid.append({
        "key": entry["key"],
        **conflict,
    })
    migrated += 1

report["errors"] = remaining_errors
report["version"] = "0.5.1"

processed = (
    [r["key"] for r in report["results"]]
    + [r["key"] for r in report["invalidTrees"]]
    + [r["key"] for r in report["errors"]]
)

expected = {c["key"] for c in report["candidates"]}

if (
    len(processed) != len(set(processed))
    or set(processed) != expected
):
    raise RuntimeError("Migration integrity check failed")

save_report(output, report)

print("=== RECOVERY MIGRATION v0.5.1 ===")
print("Migrated conflicts:", migrated)
print("Calculated results:", len(report["results"]))
print("Invalid trees:", len(report["invalidTrees"]))
print("Other errors:", len(report["errors"]))
print("Total processed:", len(processed))
print("Saved:", output)
