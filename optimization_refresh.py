
# PoE BuildLab AI — Reusable Pareto Refresh
# Automatically discovers completed cycle reports.
# No PoB calls. Immutable output snapshots.

import hashlib
from pathlib import Path

from build_constraints import evaluate_constraints
from experiment_storage import get_experiment_dir, load_report
from profile_experiment_storage import (
    load_profile_report,
    report_path,
    save_profile_report,
)
from profile_identity import profile_fingerprint
from profile_pareto import build_frontier
from profile_scheduler_v18 import historical_state


BASE_GENERATIONS = (
    ("profile_batch_v18.json", "profile_executed_v19.json"),
    ("profile_batch_v21.json", "profile_executed_v22.json"),
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finished_rows(report):
    return (
        report.get("results", [])
        + report.get("invalidTrees", [])
        + report.get("invalidCandidates", [])
    )


def measured_row(measurement):
    removes, adds = measurement["key"].split("->")
    return {
        "removeId": removes,
        "addId": adds,
        "removeName": "",
        "addName": "",
        "stats": measurement["stats"],
        "validation": measurement["validation"],
    }


def generations(profile):
    directory = report_path(
        profile, "placeholder.json"
    ).parent

    found = []

    for path in sorted(
        directory.glob("profile_batch_cycle_*.json")
    ):
        cycle_id = path.stem.removeprefix(
            "profile_batch_cycle_"
        )
        found.append((
            path.name,
            f"profile_executed_cycle_{cycle_id}.json",
        ))

    return list(BASE_GENERATIONS) + found


def verify_profile_reports(
    profile, baseline, measurements, fingerprint
):
    observed = set()
    sources = {}

    for batch_name, result_name in generations(profile):
        batch_path = report_path(profile, batch_name)
        result_path = report_path(profile, result_name)

        if not result_path.exists():
            raise RuntimeError(
                f"Unfinished generation: {result_name}"
            )

        batch = load_profile_report(profile, batch_name)
        result = load_profile_report(profile, result_name)

        if result.get("batchSha256") != digest(batch_path):
            raise RuntimeError(
                f"Batch hash mismatch: {result_name}"
            )

        if result.get("engineFingerprint") != fingerprint:
            raise RuntimeError(
                f"Engine mismatch: {result_name}"
            )

        planned = [x["key"] for x in batch["candidates"]]
        actual_rows = finished_rows(result)
        actual = [x["key"] for x in actual_rows]

        if (
            len(planned) != len(set(planned))
            or len(actual) != len(set(actual))
            or len(planned) != batch["planned"]
            or set(planned) != set(actual)
        ):
            raise RuntimeError(
                f"Incomplete or duplicated generation: {result_name}"
            )

        for saved in actual_rows:
            key = saved["key"]

            if key in observed:
                raise RuntimeError(
                    f"Duplicate measured key in profile: {key}"
                )

            measurement = measurements.get(key)

            if measurement is None or measurement["key"] != key:
                raise RuntimeError(
                    f"Missing shared measurement: {key}"
                )

            kind = measurement["kind"]

            if kind == "CALCULATED":
                if saved not in result["results"]:
                    raise RuntimeError(
                        f"Calculated result in wrong section: {key}"
                    )

                if (
                    saved["stats"] != measurement["stats"]
                    or saved["validation"]
                    != measurement["validation"]
                    or saved.get("profileFingerprint")
                    != profile_fingerprint(profile)
                ):
                    raise RuntimeError(
                        f"Measurement/profile mismatch: {key}"
                    )

                checked = evaluate_constraints(
                    baseline,
                    measured_row(measurement),
                    limits=profile["constraints"],
                )

                for field in ("status", "problems", "changes"):
                    if checked[field] != saved[field]:
                        raise RuntimeError(
                            f"Constraint mismatch: {key} {field}"
                        )

            elif kind == "INVALID_TREE":
                if (
                    saved not in result["invalidTrees"]
                    or saved != measurement
                ):
                    raise RuntimeError(
                        f"Invalid tree mismatch: {key}"
                    )

            elif kind == "INVALID_CANDIDATE":
                if (
                    saved not in result["invalidCandidates"]
                    or saved != measurement
                ):
                    raise RuntimeError(
                        f"Invalid candidate mismatch: {key}"
                    )
            else:
                raise RuntimeError(
                    f"Unknown measurement kind: {key}"
                )

            observed.add(key)

        sources[batch_name] = digest(batch_path)
        sources[result_name] = digest(result_path)

    return observed, sources


def refresh(normal, strict, engine, fingerprint):
    profiles = (normal, strict)

    xml = normal["build"]["xmlPath"]
    group = normal["build"]["skillGroup"]
    directory = get_experiment_dir(xml, group)

    if (
        strict["build"]["xmlPath"] != xml
        or strict["build"]["skillGroup"] != group
    ):
        raise RuntimeError(
            "Profiles must share the same XML and skill group"
        )

    cache_name = (
        f"pob_measurements_v19_{fingerprint[:16]}.json"
    )
    cache_path = directory / cache_name

    cache = load_report(cache_path, xml, group)

    if (
        cache.get("version") != "1.9"
        or cache.get("engineFingerprint") != fingerprint
        or cache.get("engine") != engine
    ):
        raise RuntimeError("Cache identity mismatch")

    measurements = cache["measurements"]

    if any(
        row.get("key") != key
        for key, row in measurements.items()
    ):
        raise RuntimeError("Corrupted measurement keys")

    legacy_done, _ = historical_state(
        directory, xml, group
    )

    if legacy_done & set(measurements):
        raise RuntimeError(
            "Shared measurements overlap legacy history"
        )

    baseline = load_report(
        directory / "swap_executed.json", xml, group
    )["baseline"]

    # Verify all provenance BEFORE writing any new snapshots.
    observations = []
    source_maps = []

    for profile in profiles:
        observed, sources = verify_profile_reports(
            profile, baseline, measurements, fingerprint
        )
        observations.append(observed)
        source_maps.append(sources)

    if observations[0] | observations[1] != set(measurements):
        raise RuntimeError(
            "Some cached measurements have no verified source"
        )

    ids = []
    for profile in profiles:
        directory_profile = report_path(
            profile, "placeholder.json"
        ).parent

        current_ids = {
            p.stem.removeprefix("profile_batch_cycle_")
            for p in directory_profile.glob(
                "profile_batch_cycle_*.json"
            )
        }
        ids.append(current_ids)

    if ids[0] != ids[1] or not ids[0]:
        raise RuntimeError(
            "Cycle IDs differ or no cycles exist"
        )

    cycle_id = sorted(ids[0])[-1]
    output_name = f"merged_frontier_cycle_{cycle_id}.json"

    prepared = []

    for index, profile in enumerate(profiles):
        history_name = "historical_evaluated_results.json"
        history = load_profile_report(profile, history_name)

        if history["calculated"] != len(history["results"]):
            raise RuntimeError("Historical row count mismatch")

        for name, expected in history["sourceHashes"].items():
            if digest(directory / name) != expected:
                raise RuntimeError(
                    f"Historical source changed: {name}"
                )

        rows = list(history["results"])
        historical_keys = [r["key"] for r in rows]

        if len(historical_keys) != len(set(historical_keys)):
            raise RuntimeError("Duplicate historical results")

        if set(historical_keys) & set(measurements):
            raise RuntimeError("Historical/cache overlap")

        invalid_count = 0
        new_pass = 0
        new_reject = 0

        for key, measurement in sorted(measurements.items()):
            if measurement["kind"] != "CALCULATED":
                invalid_count += 1
                continue

            checked = evaluate_constraints(
                baseline,
                measured_row(measurement),
                limits=profile["constraints"],
            )
            checked["key"] = key
            rows.append(checked)

            if checked["status"] == "PASS":
                new_pass += 1
            else:
                new_reject += 1

        frontier, unique_points = build_frontier(rows)

        pass_count = sum(
            row["status"] == "PASS" for row in rows
        )

        source_hashes = {
            "cache/" + cache_name: digest(cache_path),
            "profile/" + history_name: digest(
                report_path(profile, history_name)
            ),
        }

        for name, value in source_maps[index].items():
            source_hashes["profile/" + name] = value

        for name, value in source_maps[1 - index].items():
            source_hashes["otherProfile/" + name] = value

        for name, expected in history["sourceHashes"].items():
            source_hashes["legacy/" + name] = expected

        report = {
            "version": "cycle-refresh-1",
            "cycleId": cycle_id,
            "engineFingerprint": fingerprint,
            "sourceHashes": source_hashes,
            "historicalCalculated": len(history["results"]),
            "sharedMeasurements": len(measurements),
            "newCalculated": len(measurements) - invalid_count,
            "newInvalid": invalid_count,
            "newPass": new_pass,
            "newReject": new_reject,
            "completedUniqueAttempts": (
                len(legacy_done) + len(measurements)
            ),
            "totalCalculated": len(rows),
            "totalPass": pass_count,
            "totalReject": len(rows) - pass_count,
            "metrics": [
                "dps_percent",
                "ehp_percent",
                "mana_regen_percent",
            ],
            "frontierCount": len(frontier),
            "uniqueMetricPoints": unique_points,
            "frontier": frontier,
        }

        target = report_path(profile, output_name)

        if target.exists():
            saved = load_profile_report(profile, output_name)
            if any(
                saved.get(field) != report[field]
                for field in report
            ):
                raise RuntimeError(
                    f"Existing snapshot differs: {target}"
                )
            prepared.append((profile, report, False))
        else:
            prepared.append((profile, report, True))

    for profile, report, create in prepared:
        if create:
            save_profile_report(
                profile, output_name, report
            )

        print(
            profile["build"]["name"],
            "| calculated:", report["totalCalculated"],
            "| PASS:", report["totalPass"],
            "| REJECT:", report["totalReject"],
            "| Pareto:", report["frontierCount"],
        )

    print("Snapshot:", output_name)
    print("Cache entries:", len(measurements))
    print("Confirmed across profiles:", len(
        observations[0] | observations[1]
    ))
    print("PoB calls: 0")
