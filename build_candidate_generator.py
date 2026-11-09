
# PoE BuildLab AI — Build Candidate Generator v1
# Local Ollama Qwen3 8B.
# Structural validation only: NOT PoB/game verification.

import argparse
import hashlib
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from build_specification import load_spec, DEFENSE_TYPES

MODEL = "qwen3:8b"
OLLAMA_URL = "http://localhost:11434/api/chat"
OUTPUT_DIR = Path("generated_candidates")

FIELDS = {
    "class", "ascendancy", "mainSkill",
    "damageMechanic", "defenseType",
    "leagueStartGear", "levelingPlan",
    "strengths", "risks",
}


def validate_candidates(data, spec, expected=3):
    if not isinstance(data, dict):
        raise ValueError("Response must be an object")

    if set(data) != {"candidates"}:
        raise ValueError("Unexpected response fields")

    candidates = data["candidates"]

    if not isinstance(candidates, list):
        raise ValueError("Candidates must be a list")

    if len(candidates) != expected:
        raise ValueError(
            f"Expected {expected} candidates, got {len(candidates)}"
        )

    seen = set()

    for index, candidate in enumerate(candidates, 1):
        if not isinstance(candidate, dict):
            raise ValueError(f"Candidate {index} is not an object")

        if set(candidate) != FIELDS:
            raise ValueError(
                f"Candidate {index} has missing or extra fields: "
                f"{sorted(set(candidate) ^ FIELDS)}"
            )

        for field in FIELDS - {
            "leagueStartGear", "levelingPlan",
            "strengths", "risks",
        }:
            value = candidate[field]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Candidate {index}: invalid {field}"
                )

        if candidate["defenseType"] not in (
            DEFENSE_TYPES - {"auto"}
        ):
            raise ValueError("Candidate defenseType is invalid")

        required_class = spec["character"]["class"]
        required_ascendancy = spec["character"]["ascendancy"]
        required_skill = spec["playstyle"]["mainSkill"]
        required_defense = spec["character"]["defenseType"]

        for actual, required, field in (
            (candidate["class"], required_class, "class"),
            (candidate["ascendancy"], required_ascendancy, "ascendancy"),
            (candidate["mainSkill"], required_skill, "mainSkill"),
            (candidate["defenseType"], required_defense, "defenseType"),
        ):
            if required != "auto" and actual != required:
                raise ValueError(
                    f"Candidate {index} violates requested {field}"
                )

        for field in (
            "leagueStartGear", "levelingPlan",
            "strengths", "risks",
        ):
            values = candidate[field]
            if (
                not isinstance(values, list)
                or not values
                or len(values) > 8
                or any(
                    not isinstance(item, str)
                    or not item.strip()
                    for item in values
                )
            ):
                raise ValueError(
                    f"Candidate {index}: invalid {field}"
                )

        identity = (
            candidate["class"].casefold(),
            candidate["ascendancy"].casefold(),
            candidate["mainSkill"].casefold(),
            candidate["damageMechanic"].casefold(),
        )

        if identity in seen:
            raise ValueError("Duplicate build concept")

        seen.add(identity)

    return candidates


def make_messages(spec):
    system = """
You are Kvin, a Path of Exile 1 build research assistant.

Return ONLY valid JSON, with exactly one top-level key:
"candidates", containing exactly 3 objects.

Each object MUST contain exactly these fields:
class: string
ascendancy: string
mainSkill: string
damageMechanic: string
defenseType: string
leagueStartGear: nonempty array of strings
levelingPlan: nonempty array of strings
strengths: nonempty array of strings
risks: nonempty array of strings

defenseType must be one of:
life, energy_shield, hybrid, ward, mana.

Respect every explicit class, ascendancy, skill and defense
selection. "auto" means you must choose a concrete value.

Produce 3 meaningfully different build concepts.

Never invent PoB measurements, DPS, EHP or prices.
Do not assert that a build is patch-verified.
Do not assume access to current league patch notes.
Identify uncertain interactions in risks.
Treat budget and progression as design constraints.

These are hypotheses for future mechanical verification,
not finished builds.
""".strip()

    user = (
        "Propose three PoE1 build concepts for this "
        "specification. Respond with JSON only.\n\n"
        + json.dumps(spec, ensure_ascii=False, indent=2)
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def call_ollama(spec):
    payload = {
        "model": MODEL,
        "messages": make_messages(spec),
        "stream": False,
        "think": False,
        "format": "json",
        "options": {
            "temperature": 0,
            "num_ctx": 8192,
            "num_predict": 3072,
        },
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request, timeout=240
        ) as response:
            result = json.load(response)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(
            f"Cannot obtain Ollama response: {exc}"
        ) from exc

    if result.get("done") is not True:
        raise RuntimeError("Ollama response is incomplete")

    if result.get("done_reason") == "length":
        raise RuntimeError("Ollama response was truncated")

    content = result.get("message", {}).get("content")

    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Ollama returned empty content")

    try:
        return json.loads(content), result
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Kvin returned invalid JSON; no candidates saved"
        ) from exc


def mock_response():
    def concept(cls, asc, skill, mechanism):
        return {
            "class": cls,
            "ascendancy": asc,
            "mainSkill": skill,
            "damageMechanic": mechanism,
            "defenseType": "life",
            "leagueStartGear": [
                "Rare gear; availability not yet verified"
            ],
            "levelingPlan": [
                "Leveling progression requires verification"
            ],
            "strengths": [
                "Candidate suitable for mechanical testing"
            ],
            "risks": [
                "Mechanics, budget and PoB are unverified"
            ],
        }

    return {
        "candidates": [
            concept("Witch", "Elementalist", "Fireball", "ignite"),
            concept("Ranger", "Deadeye", "Lightning Arrow", "hit"),
            concept("Duelist", "Slayer", "Cyclone", "physical hit"),
        ]
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("spec")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--mock", action="store_true")
    mode.add_argument("--run", action="store_true")
    args = parser.parse_args()

    spec_path = Path(args.spec)
    spec = load_spec(spec_path)

    if args.mock:
        data = mock_response()
        model_info = {"mode": "mock"}
    else:
        data, raw = call_ollama(spec)
        model_info = {
            "mode": "ollama",
            "model": raw.get("model"),
            "doneReason": raw.get("done_reason"),
            "evalCount": raw.get("eval_count"),
        }

    candidates = validate_candidates(data, spec)

    digest = hashlib.sha256(
        spec_path.read_bytes()
    ).hexdigest()

    report = {
        "generatorVersion": 1,
        "specSha256": digest,
        "specPath": str(spec_path.resolve()),
        "generatedAt": datetime.now(
            timezone.utc
        ).isoformat(),
        "modelInfo": model_info,
        "verificationStatus": "UNVERIFIED_HYPOTHESIS",
        "candidates": candidates,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    from uuid import uuid4
    suffix = uuid4().hex[:8]
    name = (
        f"candidate_{digest[:12]}_"
        f"{model_info['mode']}_{suffix}.json"
    )
    destination = OUTPUT_DIR / name

    # Exclusive creation: never overwrite an earlier run.
    with destination.open("x", encoding="utf-8") as file:
        json.dump(
            report, file, ensure_ascii=False, indent=2
        )
        file.write("\n")

    print("=== BUILD CANDIDATE GENERATOR v1 ===")
    print("Mode:", model_info["mode"])
    print("Spec SHA256:", digest[:16])
    print("Candidates:", len(candidates))

    for index, candidate in enumerate(candidates, 1):
        print(
            f"{index}. {candidate['class']} / "
            f"{candidate['ascendancy']} / "
            f"{candidate['mainSkill']}"
        )

    print("Verification: UNVERIFIED_HYPOTHESIS")
    print("Saved:", destination)
    print("PoB calls: 0")


if __name__ == "__main__":
    main()
