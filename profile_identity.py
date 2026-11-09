
# PoE BuildLab AI — Profile Identity v1.1

import hashlib
import json


def profile_fingerprint(profile):
    """Stable identity of optimization requirements."""

    relevant = {
        "profileVersion": profile["profileVersion"],
        "skillGroup": profile["build"]["skillGroup"],
        "objectives": profile["objectives"],
        "constraints": profile["constraints"],
    }

    encoded = json.dumps(
        relevant,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def profile_metadata(profile):
    return {
        "profileVersion": profile["profileVersion"],
        "profileFingerprint": profile_fingerprint(profile),
        "profileName": profile["build"]["name"],
    }


def verify_profile(report, profile):
    expected = profile_fingerprint(profile)
    actual = report.get("profileFingerprint")

    if actual is None:
        raise ValueError(
            "Report has no profile identity; "
            "legacy report requires explicit migration"
        )

    if actual != expected:
        raise ValueError(
            "Profile fingerprint mismatch: "
            f"report={actual[:12]}, "
            f"current={expected[:12]}"
        )

    return True
