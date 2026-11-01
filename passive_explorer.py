
# PoE BuildLab — Passive Explorer v0.1

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from experiment_runner import evaluate

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
CANDIDATES_LUA = SRC / "passive_candidates.lua"

METRICS = (
    "combinedDPS",
    "speed",
    "totalEHP",
    "life",
    "energyShield",
    "mana",
)


def get_candidates(xml_path):
    luajit = shutil.which("luajit")
    if not luajit:
        raise RuntimeError("LuaJIT not found in PATH")

    if not CANDIDATES_LUA.is_file():
        raise FileNotFoundError(CANDIDATES_LUA)

    process = subprocess.run(
        [luajit, str(CANDIDATES_LUA), str(xml_path)],
        cwd=SRC,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        check=False,
    )

    lines = [
        line[len("RESULT_JSON:"):]
        for line in process.stdout.splitlines()
        if line.startswith("RESULT_JSON:")
    ]

    if process.returncode != 0 or len(lines) != 1:
        raise RuntimeError(
            "Candidate discovery failed:\n"
            + process.stderr[-2000:]
            + process.stdout[-1000:]
        )

    data = json.loads(lines[0])

    if data.get("ok") is not True:
        raise RuntimeError(f"Invalid candidate response: {data}")

    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        raise RuntimeError("Missing candidates list")

    return data


def explore(xml_path, limit, metric):
    discovery = get_candidates(xml_path)
    candidates = discovery["candidates"][:limit]

    baseline = evaluate(xml_path)
    baseline_stats = baseline["stats"]

    results = []
    errors = []

    for index, candidate in enumerate(candidates, 1):
        node_id = candidate["id"]
        node_name = candidate["name"]

        print(
            f"[{index}/{len(candidates)}] "
            f"{node_id} — {node_name}",
            file=sys.stderr,
            flush=True,
        )

        try:
            modified = evaluate(xml_path, node=int(node_id))
            experiment = modified.get("passiveExperiment")

            if not isinstance(experiment, dict):
                raise RuntimeError("Missing passive experiment data")

            if experiment.get("pointsSpent") != 1:
                raise RuntimeError("Unexpected passive point cost")

            changes = {}

            for key in METRICS:
                before = baseline_stats.get(key)
                after = modified["stats"].get(key)

                if (
                    type(before) not in (int, float)
                    or type(after) not in (int, float)
                ):
                    continue

                delta = after - before
                percent = (
                    delta / abs(before) * 100
                    if before != 0
                    else None
                )

                changes[key] = {
                    "before": before,
                    "after": after,
                    "delta": round(delta, 6),
                    "percent": round(percent, 3)
                    if percent is not None else None,
                }

            results.append({
                "nodeId": node_id,
                "name": node_name,
                "pointsSpent": 1,
                "changes": changes,
            })

        except Exception as exc:
            errors.append({
                "nodeId": node_id,
                "name": node_name,
                "error": str(exc),
            })

    results.sort(
        key=lambda item: (
            item["changes"].get(metric, {}).get("delta", float("-inf"))
        ),
        reverse=True,
    )

    return {
        "ok": len(errors) == 0,
        "experiment": "passive_explorer_v0.1",
        "className": discovery.get("className"),
        "level": discovery.get("level"),
        "metric": metric,
        "candidateCount": discovery.get("candidateCount"),
        "evaluated": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors,
        "limitations": [
            "Only single-node independent experiments",
            "Character's available passive points are not validated",
            "Ranking considers only the selected metric",
            "Results depend on the saved PoB configuration",
        ],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Explore passive node changes using PoB"
    )
    parser.add_argument("xml_path")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--metric",
        choices=METRICS,
        default="combinedDPS",
    )
    parser.add_argument(
        "--output",
        help="Optional output JSON file",
    )

    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be >= 1")

    xml_path = Path(args.xml_path).resolve()

    if not xml_path.is_file():
        parser.error(f"Build XML not found: {xml_path}")

    try:
        result = explore(
            xml_path,
            limit=args.limit,
            metric=args.metric,
        )

        output = json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )

        if args.output:
            Path(args.output).write_text(
                output + "\n",
                encoding="utf-8",
            )
        else:
            print(output)

        return 0 if result["ok"] else 1

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
