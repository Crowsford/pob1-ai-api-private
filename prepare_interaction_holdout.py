
import os
import shutil
from pathlib import Path

from experiment_storage import (
    get_experiment_dir,
    load_report,
    save_report,
)

xml = Path(os.environ["BUILD_XML"]).resolve()
directory = get_experiment_dir(xml, 6)

batch_path = directory / "multi_swap_batch_v12.json"
backup_path = directory / "multi_swap_batch_v12_before_holdout.json"
holdout_path = directory / "interaction_holdout_plan.json"

if backup_path.exists() or holdout_path.exists():
    raise RuntimeError("Holdout preparation already exists")

old_batch = load_report(batch_path, xml, 6)
executed = load_report(
    directory / "multi_swap_executed_v12.json", xml, 6
)

done = {
    row["key"]
    for section in ("results", "invalidTrees", "invalidCandidates")
    for row in executed.get(section, [])
}

unfinished = [
    row["key"]
    for row in old_batch["candidates"]
    if row["key"] not in done
]

if unfinished:
    raise RuntimeError(
        f"Current batch has {len(unfinished)} unfinished attempts"
    )

pool = load_report(
    directory / "multi_swap_candidate_pool.json", xml, 6
)

wanted = [
    "21974,22315->57264,65203",
    "22315,25831->57264,65203",
    "22315,47085->57264,65203",
    "25831,47085->57264,65203",
    "9392,22315->57264,65203",
    "22315,50082->57264,65203",
]

by_key = {row["key"]: row for row in pool["candidates"]}

if len(by_key) != len(pool["candidates"]):
    raise RuntimeError("Duplicate pool keys")

if any(key in done for key in wanted):
    raise RuntimeError("Some holdout experiments already executed")

candidates = []

for key in wanted:
    row = dict(by_key[key])
    if row["predictedStatus"] != "PASS":
        raise RuntimeError(f"Unexpected prediction: {key}")
    row["selectionMode"] = "interaction_holdout"
    candidates.append(row)

batch = {
    "version": "1.2",
    "xmlPath": str(xml),
    "xmlSha256": pool["xmlSha256"],
    "skillGroup": 6,
    "experimentType": "interaction_holdout",
    "fixedDpsCorrection": 0.377,
    "planned": len(candidates),
    "candidates": candidates,
}

shutil.copy2(batch_path, backup_path)
save_report(holdout_path, batch)
save_report(batch_path, batch)

print("=== INTERACTION HOLDOUT PREPARED ===")
print("Candidates:", len(candidates))
print("Fixed DPS correction: +0.377 pp")
print("Previous batch backed up:", backup_path)
print("Holdout manifest:", holdout_path)
print("Ready for executor.")
