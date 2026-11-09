
# PoE BuildLab AI — Optimization Controller
# Stage 1: read-only state inspection and integrity checks.

import argparse
import hashlib
import re
from copy import deepcopy
from pathlib import Path

from build_profile import load_build_profile
from experiment_storage import get_experiment_dir, load_report
from profile_experiment_storage import (
    load_profile_report,
    report_path,
)
from profile_executor_v19 import engine_identity

ENGINE_ID = "bababan-test-20261103"
FRONTIER = "merged_frontier_v25.json"
BATCH_PREFIX = "profile_batch_cycle_"
RESULT_PREFIX = "profile_executed_cycle_"


def sha256(path):
    return hashlib.sha256(
        Path(path).read_bytes()
    ).hexdigest()


def profiles():
    normal = load_build_profile(
        "build_profiles/bababan_test.json"
    )
    strict = deepcopy(normal)
    strict["build"]["name"] += " - Strict Recharge"
    strict["constraints"][
        "max_es_recharge_loss_percent"
    ] = 0.0
    return normal, strict


def completed(report):
    return (
        report.get("results", [])
        + report.get("invalidTrees", [])
        + report.get("invalidCandidates", [])
    )


def cycle_files(profile):
    directory = report_path(
        profile, "placeholder.json"
    ).parent

    found = {}

    for path in directory.glob(
        BATCH_PREFIX + "*.json"
    ):
        match = re.fullmatch(
            r"profile_batch_cycle_([a-z0-9_-]+)\.json",
            path.name,
        )
        if not match:
            raise RuntimeError(
                f"Unexpected cycle filename: {path.name}"
            )

        cycle_id = match.group(1)
        found[cycle_id] = path

    return dict(sorted(found.items()))


def verify_frontier(profile, other_profile, directory,
                    cache_name, fingerprint):
    cycles = cycle_files(profile)
    if not cycles:
        raise RuntimeError("No optimization cycles found")

    latest = max(cycles, key=int)
    name = f"merged_frontier_cycle_{latest}.json"

    frontier = load_profile_report(profile, name)

    if frontier.get("version") != "cycle-refresh-1":
        raise RuntimeError("Unexpected frontier version")

    if frontier.get("cycleId") != latest:
        raise RuntimeError("Frontier cycle mismatch")

    if frontier.get("engineFingerprint") != fingerprint:
        raise RuntimeError("Frontier engine mismatch")

    if "cache/" + cache_name not in frontier["sourceHashes"]:
        raise RuntimeError("Shared cache absent from frontier")

    for source_name, expected in frontier["sourceHashes"].items():
        if source_name.startswith("cache/"):
            source_path = directory / source_name[len("cache/"):]
        elif source_name.startswith("legacy/"):
            source_path = directory / source_name[len("legacy/"):]
        elif source_name.startswith("profile/"):
            source_path = report_path(
                profile, source_name[len("profile/"):]
            )
        elif source_name.startswith("otherProfile/"):
            source_path = report_path(
                other_profile,
                source_name[len("otherProfile/"):]
            )
        else:
            raise RuntimeError(
                f"Unknown frontier source: {source_name}"
            )

        if sha256(source_path) != expected:
            raise RuntimeError(
                f"Stale frontier source: {source_name}"
            )

    return frontier


def inspect_profile(profile, other_profile,
                    directory, cache, fingerprint):
    frontier = verify_frontier(
        profile, other_profile, directory,
        cache["cacheName"], fingerprint,
    )

    batches = cycle_files(profile)
    cycle_keys = set()
    cycle_summary = []

    for cycle_id, batch_path in batches.items():
        batch_name = batch_path.name
        result_name = (
            RESULT_PREFIX + cycle_id + ".json"
        )

        batch = load_profile_report(
            profile, batch_name
        )

        if batch.get("batchId") != cycle_id:
            raise RuntimeError(
                f"Batch ID mismatch: {cycle_id}"
            )

        if batch.get("engineFingerprint") != fingerprint:
            raise RuntimeError(
                f"Batch engine mismatch: {cycle_id}"
            )

        candidates = batch["candidates"]
        keys = [c["key"] for c in candidates]

        if (
            len(keys) != len(set(keys))
            or len(keys) != batch["planned"]
        ):
            raise RuntimeError(
                f"Invalid batch candidates: {cycle_id}"
            )

        if cycle_keys.intersection(keys):
            raise RuntimeError(
                f"Duplicate keys across cycles: {cycle_id}"
            )

        cycle_keys.update(keys)

        result_path = report_path(
            profile, result_name
        )

        if not result_path.exists():
            finished = []
        else:
            result = load_profile_report(
                profile, result_name
            )

            if result.get("batchSha256") != sha256(batch_path):
                raise RuntimeError(
                    f"Batch hash mismatch: {cycle_id}"
                )

            if result.get("engineFingerprint") != fingerprint:
                raise RuntimeError(
                    f"Result engine mismatch: {cycle_id}"
                )

            finished = completed(result)

        finished_keys = [r["key"] for r in finished]

        if len(finished_keys) != len(set(finished_keys)):
            raise RuntimeError(
                f"Duplicate results: {cycle_id}"
            )

        if not set(finished_keys).issubset(set(keys)):
            raise RuntimeError(
                f"Unexpected result keys: {cycle_id}"
            )

        for row in finished:
            key = row["key"]
            measurement = cache["measurements"].get(key)

            if measurement is None:
                raise RuntimeError(
                    f"Missing shared measurement: {key}"
                )

            if measurement.get("key") != key:
                raise RuntimeError(
                    f"Measurement key mismatch: {key}"
                )

            if "stats" in row:
                if (
                    measurement.get("kind") != "CALCULATED"
                    or row["stats"] != measurement["stats"]
                    or row["validation"] != measurement["validation"]
                ):
                    raise RuntimeError(
                        f"Measurement data mismatch: {key}"
                    )
            else:
                if row != measurement:
                    raise RuntimeError(
                        f"Invalid measurement mismatch: {key}"
                    )

        cycle_summary.append({
            "id": cycle_id,
            "planned": len(keys),
            "finished": len(finished_keys),
            "complete": len(finished_keys) == len(keys),
        })

    return frontier, cycle_summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", nargs="?", default="status",
        choices=["status", "refresh", "plan", "execute"],
    )
    parser.add_argument(
        "--engine-id", default=ENGINE_ID
    )
    parser.add_argument(
        "--size", type=int, default=10
    )
    parser.add_argument(
        "--write", action="store_true"
    )
    parser.add_argument(
        "--batch-id"
    )
    parser.add_argument(
        "--limit", type=int, default=10
    )
    parser.add_argument(
        "--execute", action="store_true"
    )

    args = parser.parse_args()

    normal, strict = profiles()

    if args.command == "execute":
        import re
        from optimization_executor import run

        if not args.batch_id or not re.fullmatch(
            r"\d{4,}", args.batch_id
        ):
            parser.error(
                "execute requires --batch-id, e.g. 0002"
            )

        if args.limit < 1:
            parser.error("--limit must be positive")

        print("=== OPTIMIZATION CONTROLLER EXECUTE ===")
        print("Cycle:", args.batch_id)
        print(
            "Mode:",
            "EXECUTE" if args.execute else "DRY RUN",
            flush=True,
        )

        for strict_mode in (False, True):
            argv = [
                "--batch-id", args.batch_id,
                "--engine-id", args.engine_id,
                "--limit", str(args.limit),
            ]

            if strict_mode:
                argv.append("--strict-recharge")

            if args.execute:
                argv.append("--execute")

            run(argv)

        return

    if args.command == "plan":
        from optimization_plan import plan
        engine, fingerprint = engine_identity(args.engine_id)
        plan(
            normal, strict, engine, fingerprint,
            size=args.size,
            write=args.write,
        )
        return

    if args.command == "refresh":
        from optimization_refresh import refresh
        engine, fingerprint = engine_identity(args.engine_id)
        refresh(normal, strict, engine, fingerprint)
        return

    xml = normal["build"]["xmlPath"]
    group = normal["build"]["skillGroup"]
    directory = get_experiment_dir(xml, group)

    engine, fingerprint = engine_identity(
        args.engine_id
    )

    cache_name = (
        f"pob_measurements_v19_{fingerprint[:16]}.json"
    )

    cache = load_report(
        directory / cache_name, xml, group
    )

    if (
        cache.get("engineFingerprint") != fingerprint
        or cache.get("engine") != engine
        or cache.get("version") != "1.9"
    ):
        raise RuntimeError("Shared cache identity mismatch")

    measurements = cache["measurements"]

    kinds = {}
    for key, row in measurements.items():
        if row["key"] != key:
            raise RuntimeError("Cache key mismatch")
        kind = row["kind"]
        kinds[kind] = kinds.get(kind, 0) + 1

    cache_info = {
        "cacheName": cache_name,
        "measurements": measurements,
    }

    print("=== POE BUILDLAB OPTIMIZATION CONTROLLER ===")
    print("Mode: READ-ONLY STATUS")
    print("Engine:", args.engine_id)
    print("Fingerprint:", fingerprint[:16])
    print("Shared measurements:", len(measurements))
    print("Calculated:", kinds.get("CALCULATED", 0))
    print("Invalid trees:", kinds.get("INVALID_TREE", 0))
    print(
        "Invalid candidates:",
        kinds.get("INVALID_CANDIDATE", 0),
    )

    all_cycles = []

    for profile, other in (
        (normal, strict),
        (strict, normal),
    ):
        frontier, cycles = inspect_profile(
            profile, other, directory,
            cache_info, fingerprint,
        )

        print("\nPROFILE:", profile["build"]["name"])
        print("Calculated total:", frontier["totalCalculated"])
        print("PASS:", frontier["totalPass"])
        print("REJECT:", frontier["totalReject"])
        print("Pareto combinations:", frontier["frontierCount"])
        print("Pareto points:", frontier["uniqueMetricPoints"])

        for cycle in cycles:
            print(
                "Cycle", cycle["id"],
                f'{cycle["finished"]}/{cycle["planned"]}',
                "COMPLETE" if cycle["complete"]
                else "INCOMPLETE",
            )

        all_cycles.append({
            cycle["id"]: cycle for cycle in cycles
        })

    if set(all_cycles[0]) != set(all_cycles[1]):
        raise RuntimeError(
            "Profiles have different cycle IDs"
        )

    if any(
        not cycle["complete"]
        for cycles in all_cycles
        for cycle in cycles.values()
    ):
        print("\nSTATUS: INCOMPLETE CYCLES")
    else:
        print("\nSTATUS: VERIFIED")
        print("Existing cycles complete: YES")

    print("PoB calls: 0")
    print("Files modified: 0")


if __name__ == "__main__":
    main()
