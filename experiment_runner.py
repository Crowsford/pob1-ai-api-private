
# PoE BuildLab — Experiment Runner v0.1
import json
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
SRC_DIR = PROJECT_DIR / "src"
EVALUATOR = SRC_DIR / "headless_evaluate.lua"

RESULT_PREFIX = "RESULT_JSON:"
TIMEOUT_SECONDS = 90


def evaluate(
    xml_path: str | Path,
    level: int | None = None,
    node: int | None = None,
) -> dict:
    xml_path = Path(xml_path).expanduser().resolve()

    if not xml_path.is_file():
        raise FileNotFoundError(f"Build XML not found: {xml_path}")

    if not EVALUATOR.is_file():
        raise FileNotFoundError(f"Lua evaluator not found: {EVALUATOR}")

    luajit = shutil.which("luajit")
    if not luajit:
        raise RuntimeError("LuaJIT executable not found in PATH")

    command = [
        luajit,
        str(EVALUATOR),
        str(xml_path),
    ]

    if level is not None:
        if not 1 <= level <= 100:
            raise ValueError("Level must be between 1 and 100")
        command.append(str(level))
    if node is not None:
        if not isinstance(node, int) or node <= 0:
            raise ValueError("Node ID must be a positive integer")

        # Lua currently expects level in argument 2 and node in argument 3.
        # If level was not specified, use the level from the source XML.
        if level is None:
            import xml.etree.ElementTree as ET

            root = ET.parse(xml_path).getroot()
            build_element = root.find("Build")
            if build_element is None:
                raise ValueError("Build section not found in XML")

            source_level = build_element.get("level")
            if source_level is None:
                raise ValueError("Character level not found in XML")

            command.append(str(int(source_level)))

        command.append(str(node))
    try:
        process = subprocess.run(
            command,
            cwd=SRC_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"PoB calculation timed out after {TIMEOUT_SECONDS}s"
        ) from exc

    result_lines = [
        line[len(RESULT_PREFIX):].strip()
        for line in process.stdout.splitlines()
        if line.startswith(RESULT_PREFIX)
    ]

    if len(result_lines) != 1:
        raise RuntimeError(
            "Expected exactly one RESULT_JSON line.\n"
            f"Exit code: {process.returncode}\n"
            f"STDOUT:\n{process.stdout[-3000:]}\n"
            f"STDERR:\n{process.stderr[-3000:]}"
        )

    try:
        result = json.loads(result_lines[0])
    except json.JSONDecodeError as exc:
        raise RuntimeError("Invalid JSON returned by PoB") from exc

    if not isinstance(result, dict):
        raise RuntimeError("PoB result must be a JSON object")

    if process.returncode != 0 or result.get("ok") is not True:
        raise RuntimeError(
            f"PoB calculation failed: {result.get('error', 'unknown error')}"
            f"\nExit code: {process.returncode}"
            f"\nSTDERR:\n{process.stderr[-3000:]}"
        )

    return result

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Evaluate a PoE build using headless Path of Building"
    )
    parser.add_argument("xml_path", help="Path to the build XML")




    parser.add_argument(
        "--level",
        type=int,
        default=None,
        help="Override character level (1-100)",
    )

    parser.add_argument(
        "--node",
        type=int,
        default=None,
        help="Allocate a passive node by ID",
    )


    args = parser.parse_args()

    try:
        result = evaluate(args.xml_path, level=args.level, node=args.node)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
