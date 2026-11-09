
# PoE BuildLab AI — Build Profile Loader v1.0

import json
import math
from pathlib import Path

from build_constraints import LIMITS

ROOT = Path(__file__).resolve().parent
PROFILE_VERSION = "1.0"


def load_build_profile(filename):
    path = Path(filename).resolve()

    with path.open("r", encoding="utf-8") as file:
        profile = json.load(file)

    if profile.get("profileVersion") != PROFILE_VERSION:
        raise ValueError("Unsupported build profile version")

    build = profile.get("build")
    if not isinstance(build, dict):
        raise ValueError("Missing build configuration")

    name = build.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Invalid build name")

    skill_group = build.get("skillGroup")
    if type(skill_group) is not int or skill_group < 1:
        raise ValueError("Invalid skill group")

    xml_raw = build.get("xmlPath")
    if not isinstance(xml_raw, str) or not xml_raw:
        raise ValueError("Missing XML path")

    xml = Path(xml_raw)
    if not xml.is_absolute():
        xml = ROOT / xml

    xml = xml.resolve()
    if not xml.is_file():
        raise FileNotFoundError(xml)

    limits = profile.get("constraints")
    if not isinstance(limits, dict):
        raise ValueError("Missing constraints")

    missing = set(LIMITS) - set(limits)
    unknown = set(limits) - set(LIMITS)

    if missing or unknown:
        raise ValueError(
            f"Invalid constraint keys: "
            f"missing={sorted(missing)}, "
            f"unknown={sorted(unknown)}"
        )

    for key, default in LIMITS.items():
        candidate = limits[key]

        if isinstance(default, bool):
            if type(candidate) is not bool:
                raise ValueError(f"Invalid boolean: {key}")
        else:
            if (
                type(candidate) not in (int, float)
                or not math.isfinite(candidate)
                or candidate < 0
            ):
                raise ValueError(f"Invalid numeric limit: {key}")

    objectives = profile.get("objectives", {})
    maximize = objectives.get("maximize", [])

    if (
        not isinstance(maximize, list)
        or not maximize
        or any(
            not isinstance(item, str) or not item
            for item in maximize
        )
    ):
        raise ValueError("Invalid optimization objectives")

    result = dict(profile)
    result["build"] = dict(build)
    result["build"]["xmlPath"] = str(xml)
    result["constraints"] = dict(limits)

    return result


def print_profile(profile):
    build = profile["build"]

    print("=== BUILD PROFILE ===")
    print("Name:", build["name"])
    print("XML:", build["xmlPath"])
    print("Skill group:", build["skillGroup"])
    print("Objectives:", profile["objectives"]["maximize"])

    print("\nConstraints:")
    for key, value in profile["constraints"].items():
        print(f"  {key}: {value}")
