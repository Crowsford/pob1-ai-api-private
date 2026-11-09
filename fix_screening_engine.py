
from pathlib import Path

path = Path("screening_engine.py")
source = path.read_text(encoding="utf-8")

start_marker = '            row = {\n'
end_marker = '        if xml_sha256(xml_path) != xml_hash:\n'

start = source.index(start_marker, source.index("        except Exception as exc:"))
end = source.index(end_marker, start)

old = source[start:end]

if 'result["stats"]' not in old:
    raise RuntimeError("Unexpected code structure")

# This block is currently inside except (12 spaces).
# Move it into try/except/else (8 spaces for else,
# 12 spaces for its contents).
replacement = (
    "        else:\n"
    "            validation = verify_result(\n"
    "                baseline, result, candidate\n"
    "            )\n\n"
    + old
)

source = source[:start] + replacement + source[end:]
path.write_text(source, encoding="utf-8")

print("Fixed: successful evaluation is now in try/except/else")
