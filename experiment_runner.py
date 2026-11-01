
# PoE BuildLab — Experiment Runner v0.2

import argparse
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
SRC_DIR = PROJECT_DIR / "src"
EVALUATOR = SRC_DIR / "headless_evaluate.lua"

RESULT_PREFIX = "RESULT_JSON:"
TIMEOUT_SECONDS = 90


def read_build_level(xml_path: Path) -> int:
    root = ET.parse(xml_path).getroot()
    build_element = root.find("Build")

    if build_element is None:
        raise ValueError("Build section not found in XML")

    raw_level = build_element.get("level")

    if raw_level is None:
        raise ValueError("Character level not found in XML")

    level = int(raw_level)

    if not 1 <= level <= 100:
        raise ValueError("Invalid character level in XML")

    return level


def parse_nodes(raw: str) -> list[int]:
    parts = raw.split(",")

    if not 1 <= len(parts) <= 10:
        raise ValueError("Specify between 1 and 10 passive nodes")

    nodes = []

    for part in parts:
        part = part.strip()

        if not part or not part.isdecimal():
            raise ValueError(f"Invalid passive node ID: {part!r}")

        node_id = int(part)

        if node_id <= 0:
            raise ValueError("Passive node IDs must be positive")

        nodes.append(node_id)

    if len(nodes) != len(set(nodes)):
        raise ValueError("Duplicate passive node IDs")

    return nodes


def evaluate(
    xml_path: str | Path,
    level: int | None = None,
    node: int | None = None,
    nodes: list[int] | None = None,
) -> dict:
    xml_path = Path(xml_path).expanduser().resolve()

    if not xml_path.is_file():
        raise FileNotFoundError(f"Build XML not found: {xml_path}")

    if not EVALUATOR.is_file():
        raise FileNotFoundError(f"Lua evaluator not found: {EVALUATOR}")

    if node is not None and nodes is not None:
        raise ValueError("Use either node or nodes, not both")

    if level is not None:
        if type(level) is not int or not 1 <= level <= 100:
            raise ValueError("Level must be an integer between 1 and 100")

    selected_nodes = []

    if node is not None:
        selected_nodes = [node]
    elif nodes is not None:
        selected_nodes = list(nodes)

    if selected_nodes:
        if not 1 <= len(selected_nodes) <= 10:
            raise ValueError("Specify between 1 and 10 passive nodes")

        if any(type(n) is not int or n <= 0 for n in selected_nodes):
            raise ValueError("Passive node IDs must be positive integers")

        if len(selected_nodes) != len(set(selected_nodes)):
            raise ValueError("Duplicate passive node IDs")

    luajit = shutil.which("luajit")

    if not luajit:
        raise RuntimeError("LuaJIT executable not found in PATH")

    command = [
        luajit,
        str(EVALUATOR),
        str(xml_path),
    ]

    # Lua evaluator expects:
    # arg[1] = XML path
    # arg[2] = level
    # arg[3] = comma-separated passive node IDs
    if selected_nodes:
        effective_level = (
            level if level is not None
            else read_build_level(xml_path)
        )

        command.append(str(effective_level))
        command.append(",".join(str(n) for n in selected_nodes))

    elif level is not None:
        command.append(str(level))

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
    parser = argparse.ArgumentParser(
        description="Evaluate PoE builds using headless Path of Building"
    )

    parser.add_argument(
        "xml_path",
        help="Path to the build XML",
    )

    parser.add_argument(
        "--level",
        type=int,
        default=None,
        help="Override character level (1-100)",
    )

    group = parser.add_mutually_exclusive_group()

    group.add_argument(
        "--node",
        type=int,
        help="Allocate one passive node",
    )

    group.add_argument(
        "--nodes",
        type=parse_nodes,
        help="Allocate 1-10 passive nodes, e.g. 50082,1891",
    )

    args = parser.parse_args()

    try:
        result = evaluate(
            args.xml_path,
            level=args.level,
            node=args.node,
            nodes=args.nodes,
        )

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
