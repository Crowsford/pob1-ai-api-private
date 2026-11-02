
# PoE BuildLab — Experiment Storage v0.1

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPERIMENTS_DIR = ROOT / "experiments"


def xml_sha256(xml_path):
    path = Path(xml_path).resolve()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get_experiment_dir(xml_path, skill_group=6):
    path = Path(xml_path).resolve()
    digest = xml_sha256(path)

    # A different XML or skill group gets a different directory.
    experiment_dir = (
        EXPERIMENTS_DIR / f"{path.stem}-sg{skill_group}-{digest[:12]}"
    )

    experiment_dir.mkdir(parents=True, exist_ok=True)
    return experiment_dir


def metadata(xml_path, skill_group=6):
    path = Path(xml_path).resolve()

    return {
        "xmlPath": str(path),
        "xmlSha256": xml_sha256(path),
        "skillGroup": skill_group,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }


def validate_source(report, xml_path, skill_group=6):
    expected_hash = xml_sha256(xml_path)
    saved_hash = report.get("xmlSha256")

    if not saved_hash:
        raise ValueError(
            "Report has no XML SHA-256. "
            "Legacy results cannot be trusted automatically."
        )

    if saved_hash.lower() != expected_hash.lower():
        raise ValueError(
            "XML SHA-256 mismatch. "
            "Report belongs to a different build configuration."
        )

    if report.get("skillGroup") != skill_group:
        raise ValueError("Skill group mismatch")

    return True


def save_report(path, report):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = path.with_suffix(path.suffix + ".tmp")

    temp_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    os.replace(temp_path, path)


def load_report(path, xml_path, skill_group=6):
    path = Path(path)

    report = json.loads(path.read_text(encoding="utf-8"))
    validate_source(report, xml_path, skill_group)

    return report
