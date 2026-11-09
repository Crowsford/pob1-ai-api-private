
# PoE BuildLab AI — Profile Executor v2.4
# Shared measurements, isolated profile evaluations.
# Default mode is read-only. --execute enables PoB calls.

import argparse
import hashlib
import json
import re
from pathlib import Path

from build_constraints import evaluate_constraints
from build_profile import load_build_profile
from build_validator import validate_experiment
from experiment_runner import evaluate
from experiment_storage import (
    get_experiment_dir,
    load_report,
    save_report,
    xml_sha256,
)
from profile_experiment_storage import (
    load_profile_report,
    report_path,
    save_profile_report,
)
from profile_identity import profile_fingerprint

BATCH = "profile_batch_v21.json"
RESULT = "profile_executed_v22.json"

CODE_FILES = (
    "experiment_runner.py",
    "build_validator.py",
    "src/headless_evaluate.lua",
)


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def engine_identity(engine_id):
    if not engine_id or len(engine_id) > 128:
        raise ValueError("Invalid engine identifier")

    files = {}
    for name in CODE_FILES:
        path = Path(name)
        if not path.is_file():
            raise FileNotFoundError(
                f"Required computation source missing: {name}"
            )
        files[name] = sha_file(path)

    payload = {
        "engineId": engine_id,
        "sourceFiles": files,
        "cacheFormat": "1.9",
    }
    encoded = json.dumps(
        payload, sort_keys=True
    ).encode("utf-8")

    return payload, hashlib.sha256(encoded).hexdigest()


def completed(report):
    return (
        report.get("results", [])
        + report.get("invalidTrees", [])
        + report.get("invalidCandidates", [])
    )


def validate_key(candidate):
    removes = candidate["removeIds"]
    adds = candidate["addIds"]

    if (
        not isinstance(removes, list)
        or not isinstance(adds, list)
        or len(removes) != 2
        or len(adds) != 2
        or any(type(x) is not int or x < 1
               for x in removes + adds)
        or len(set(removes + adds)) != 4
    ):
        raise ValueError("Invalid double swap")

    key = (
        ",".join(map(str, sorted(removes)))
        + "->"
        + ",".join(map(str, sorted(adds)))
    )

    if candidate["key"] != key:
        raise ValueError(f"Noncanonical key: {candidate['key']}")

    return key


def evaluate_in_pob(xml, group, candidate, baseline):
    key = validate_key(candidate)
    removes = candidate["removeIds"]
    adds = candidate["addIds"]

    try:
        result = evaluate(
            xml,
            nodes=adds,
            remove_nodes=removes,
            skill_group=group,
        )
    except Exception as exc:
        message = str(exc)

        if "TREE_CONFLICT|" in message:
            match = re.search(
                r"TREE_CONFLICT\|requested=(\d+)"
                r"\|disconnected=([0-9,]*)",
                message,
            )
            if match is None:
                raise

            return {
                "key": key,
                "kind": "INVALID_TREE",
                "requested": int(match.group(1)),
                "disconnected": [
                    int(x)
                    for x in match.group(2).split(",")
                    if x
                ],
            }

        if "Node requires more than one point:" in message:
            return {
                "key": key,
                "kind": "INVALID_CANDIDATE",
                "reason": "MULTI_POINT_REQUIRED",
                "error": message.splitlines()[0],
            }

        raise

    removed = sorted(
        int(x["nodeId"])
        for x in result["removalExperiment"]["nodes"]
    )
    added = sorted(
        int(x["nodeId"])
        for x in result["passiveExperiment"]["nodes"]
    )

    if removed != sorted(removes):
        raise RuntimeError(f"Removed node mismatch: {key}")

    if added != sorted(adds):
        raise RuntimeError(f"Added node mismatch: {key}")

    if result["passivePointsUsed"] != baseline["passivePointsUsed"]:
        raise RuntimeError(f"Passive point count mismatch: {key}")

    validation = validate_experiment(baseline, result)

    return {
        "key": key,
        "kind": "CALCULATED",
        "removeIds": removes,
        "addIds": adds,
        "stats": result["stats"],
        "validation": validation,
        "passivePointsUsed": result["passivePointsUsed"],
    }


def evaluate_for_profile(measurement, candidate,
                         baseline, limits):
    key = measurement["key"]
    kind = measurement["kind"]

    if kind != "CALCULATED":
        return dict(measurement)

    row = {
        "removeId": ",".join(map(str, candidate["removeIds"])),
        "addId": ",".join(map(str, candidate["addIds"])),
        "removeName": "",
        "addName": "",
        "stats": measurement["stats"],
        "validation": measurement["validation"],
    }

    checked = evaluate_constraints(
        baseline, row, limits=limits
    )

    return {
        "key": key,
        "removeIds": candidate["removeIds"],
        "addIds": candidate["addIds"],
        "status": checked["status"],
        "problems": checked["problems"],
        "changes": checked["changes"],
        "stats": measurement["stats"],
        "validation": measurement["validation"],
        "predictedStatus": candidate["predictedStatus"],
        "profileFingerprint": None,  # filled below
    }


def run(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        default="build_profiles/bababan_test.json"
    )
    parser.add_argument(
        "--strict-recharge", action="store_true"
    )
    parser.add_argument(
        "--engine-id", required=True
    )
    parser.add_argument(
        "--batch-id", required=True
    )
    parser.add_argument(
        "--limit", type=int, default=10
    )
    parser.add_argument(
        "--execute", action="store_true"
    )
    args = parser.parse_args(argv)

    if args.limit < 1:
        parser.error("--limit must be positive")

    if not re.fullmatch(
        r"[a-z0-9][a-z0-9_-]{0,31}",
        args.batch_id,
    ):
        parser.error("Invalid --batch-id")

    profile = load_build_profile(args.profile)

    if args.strict_recharge:
        from copy import deepcopy
        profile = deepcopy(profile)
        profile["build"]["name"] += " - Strict Recharge"
        profile["constraints"][
            "max_es_recharge_loss_percent"
        ] = 0.0

    xml = Path(profile["build"]["xmlPath"]).resolve()
    group = profile["build"]["skillGroup"]
    digest = xml_sha256(xml)
    directory = get_experiment_dir(xml, group)

    engine, fingerprint = engine_identity(args.engine_id)

    BATCH = (
        f"profile_batch_cycle_{args.batch_id}.json"
    )
    RESULT = (
        f"profile_executed_cycle_{args.batch_id}.json"
    )

    batch = load_profile_report(profile, BATCH)
    if batch.get("version") != "2.4":
        raise RuntimeError("Unexpected batch version")

    if batch.get("engineFingerprint") != fingerprint:
        raise RuntimeError(
            "Scheduler/Executor engine fingerprint mismatch"
        )

    if batch.get("batchId") != args.batch_id:
        raise RuntimeError("Batch ID mismatch")

    frontier_name = batch.get("frontierFile")
    pool_name = batch.get("poolFile")

    # Cyclic batches must reference the preceding
    # completed cycle's immutable Pareto snapshot.
    if not re.fullmatch(r"\d{4,}", args.batch_id):
        raise RuntimeError(
            "Optimization cycles require numeric batch IDs"
        )

    cycle_number = int(args.batch_id)

    if cycle_number < 2:
        raise RuntimeError(
            "Cycle executor starts at 0002; "
            "cycle 0001 was handled by the legacy adapter"
        )

    expected_frontier = (
        f"merged_frontier_cycle_{cycle_number - 1:04d}.json"
    )

    if frontier_name != expected_frontier:
        raise RuntimeError(
            "Unexpected frontier source: "
            f"{frontier_name}, expected {expected_frontier}"
        )

    if pool_name != "multi_swap_candidate_pool_fullstats_v16.json":
        raise RuntimeError("Unexpected pool source")

    if sha_file(
        report_path(profile, frontier_name)
    ) != batch.get("frontierSha256"):
        raise RuntimeError(
            "Frontier changed since batch scheduling"
        )

    if sha_file(
        directory / pool_name
    ) != batch.get("poolSha256"):
        raise RuntimeError(
            "Candidate pool changed since scheduling"
        )

    candidates = batch["candidates"]
    keys = [validate_key(x) for x in candidates]

    if len(keys) != len(set(keys)):
        raise RuntimeError("Duplicate batch keys")
    if len(keys) != batch["planned"]:
        raise RuntimeError("Batch count mismatch")

    batch_path = report_path(profile, BATCH)
    batch_sha = sha_file(batch_path)

    baseline = load_report(
        directory / "swap_executed.json", xml, group
    )["baseline"]

    cache_path = directory / (
        f"pob_measurements_v19_{fingerprint[:16]}.json"
    )

    cache_identity = {
        "version": "1.9",
        "xmlPath": str(xml),
        "xmlSha256": digest,
        "skillGroup": group,
        "engine": engine,
        "engineFingerprint": fingerprint,
    }

    if cache_path.exists():
        cache = load_report(cache_path, xml, group)
        for field, expected in cache_identity.items():
            if cache.get(field) != expected:
                raise RuntimeError(
                    f"Cache identity mismatch: {field}"
                )
    else:
        cache = {
            **cache_identity,
            "measurements": {},
        }

    measurements = cache["measurements"]
    if not isinstance(measurements, dict):
        raise RuntimeError("Invalid cache measurements")

    output_path = report_path(profile, RESULT)
    evaluation_identity = {
        "version": "2.4",
        "batchSha256": batch_sha,
        "engineFingerprint": fingerprint,
        "constraints": profile["constraints"],
    }

    if output_path.exists():
        evaluated = load_profile_report(profile, RESULT)
        for field, expected in evaluation_identity.items():
            if evaluated.get(field) != expected:
                raise RuntimeError(
                    f"Profile result mismatch: {field}"
                )
    else:
        evaluated = {
            **evaluation_identity,
            "results": [],
            "invalidTrees": [],
            "invalidCandidates": [],
        }

    existing = completed(evaluated)
    processed_keys = [row["key"] for row in existing]

    if len(processed_keys) != len(set(processed_keys)):
        raise RuntimeError("Duplicate profile results")

    if not set(processed_keys).issubset(set(keys)):
        raise RuntimeError(
            "Profile result contains keys outside batch"
        )

    for key in processed_keys:
        if key not in measurements:
            raise RuntimeError(
                f"Profile result lacks shared measurement: {key}"
            )

    remaining = [
        candidate for candidate in candidates
        if candidate["key"] not in processed_keys
    ]

    print("=== OPTIMIZATION EXECUTOR ===")
    print("Profile:", profile["build"]["name"])
    print("Engine ID:", args.engine_id)
    print("Engine fingerprint:", fingerprint[:16])
    print("Current batch:", len(candidates))
    print("Already evaluated:", len(processed_keys))
    print("Pending:", len(remaining))
    print(
        "Reusable measurements:",
        sum(c["key"] in measurements for c in remaining)
    )
    print(
        "New PoB calculations needed:",
        sum(c["key"] not in measurements for c in remaining)
    )

    if not args.execute:
        print("DRY RUN: no files modified, no PoB calls")
        return

    attempted = 0
    reused = 0
    calculated = 0

    for candidate in remaining[:args.limit]:
        key = candidate["key"]

        if xml_sha256(xml) != digest:
            raise RuntimeError("Build XML changed")

        if key in measurements:
            measurement = measurements[key]
            reused += 1
            origin = "CACHE"
        else:
            measurement = evaluate_in_pob(
                xml, group, candidate, baseline
            )

            if xml_sha256(xml) != digest:
                raise RuntimeError("Build XML changed")

            measurements[key] = measurement

            # Save raw measurement BEFORE evaluation,
            # so recovery cannot require a second PoB call.
            save_report(cache_path, cache)
            calculated += 1
            origin = "PoB"

        if measurement.get("key") != key:
            raise RuntimeError("Measurement key mismatch")

        outcome = evaluate_for_profile(
            measurement,
            candidate,
            baseline,
            profile["constraints"],
        )

        kind = measurement["kind"]

        if kind == "CALCULATED":
            outcome["profileFingerprint"] = (
                profile_fingerprint(profile)
            )
            evaluated["results"].append(outcome)
            status = outcome["status"]
        elif kind == "INVALID_TREE":
            evaluated["invalidTrees"].append(outcome)
            status = kind
        elif kind == "INVALID_CANDIDATE":
            evaluated["invalidCandidates"].append(outcome)
            status = kind
        else:
            raise RuntimeError(f"Unknown measurement kind: {kind}")

        if xml_sha256(xml) != digest:
            raise RuntimeError("Build XML changed")

        save_profile_report(profile, RESULT, evaluated)
        attempted += 1

        print(f"[{attempted}] {key}: {status} ({origin})",
              flush=True)

    done = completed(evaluated)
    done_keys = {x["key"] for x in done}

    print("\n=== PROFILE EXECUTOR SUMMARY ===")
    print("Processed this run:", attempted)
    print("Reused measurements:", reused)
    print("New PoB calls:", calculated)
    print("Total profile results:", len(done))
    print("Remaining:", sum(k not in done_keys for k in keys))
    print("Shared cache:", cache_path)
    print("Profile report:", output_path)
    print("Legacy reports: UNCHANGED")


if __name__ == "__main__":
    run()
