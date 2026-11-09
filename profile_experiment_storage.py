
# PoE BuildLab AI — Profile Experiment Storage v1.2
# Isolated evaluation reports. Legacy files remain untouched.

from pathlib import Path

from experiment_storage import (
    get_experiment_dir,
    load_report,
    save_report,
    xml_sha256,
)
from profile_identity import (
    profile_fingerprint,
    profile_metadata,
    verify_profile,
)


def profile_directory(profile):
    build = profile["build"]

    base = get_experiment_dir(
        build["xmlPath"],
        build["skillGroup"],
    )

    return (
        base
        / "profiles"
        / profile_fingerprint(profile)
    )


def report_path(profile, filename):
    if (
        not isinstance(filename, str)
        or not filename.endswith(".json")
        or Path(filename).name != filename
        or filename in (".", "..")
        or "\\" in filename
        or "/" in filename
    ):
        raise ValueError("Invalid profile report filename")

    return profile_directory(profile) / filename


def source_identity(profile):
    build = profile["build"]
    xml = Path(build["xmlPath"]).resolve()

    return {
        "xmlPath": str(xml),
        "xmlSha256": xml_sha256(xml),
        "skillGroup": build["skillGroup"],
    }


def save_profile_report(profile, filename, data):
    """Write only into the profile-specific directory."""

    if not isinstance(data, dict):
        raise ValueError("Report data must be a dictionary")

    path = report_path(profile, filename)

    identity = {
        **source_identity(profile),
        **profile_metadata(profile),
    }

    # Prevent accidental replacement of identity fields.
    for key, expected in identity.items():
        if key in data and data[key] != expected:
            raise ValueError(
                f"Conflicting report identity: {key}"
            )

    if path.exists():
        load_profile_report(profile, filename)

    report = {
        **data,
        **identity,
    }

    save_report(path, report)

    return path


def load_profile_report(profile, filename):
    path = report_path(profile, filename)
    build = profile["build"]

    report = load_report(
        path,
        build["xmlPath"],
        build["skillGroup"],
    )

    verify_profile(report, profile)

    expected = source_identity(profile)

    for key, value in expected.items():
        if report.get(key) != value:
            raise ValueError(
                f"Profile report source mismatch: {key}"
            )

    return report
