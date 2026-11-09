
from pathlib import Path
from experiment_runner import evaluate

root = Path(__file__).resolve().parent

builds = {
    "OLD (Wands)": root / "test_builds" / "BabaBan_current.xml",
    "CORRECTED (Staff)": root / "test_builds" / "BabaBan_corrected.xml",
}

keys = [
    "combinedDPS",
    "totalEHP",
    "energyShield",
    "blockChance",
    "spellBlockChance",
    "fireResist",
    "coldResist",
    "lightningResist",
    "manaUnreserved",
    "manaRegen",
]

results = {}

for name, path in builds.items():
    results[name] = evaluate(str(path), skill_group=6)["stats"]

print("\n=== WEAPON CONFIGURATION COMPARISON ===")

for key in keys:
    old = results["OLD (Wands)"].get(key)
    new = results["CORRECTED (Staff)"].get(key)

    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        change = new - old
        print(f"{key}: {old:.2f} -> {new:.2f} ({change:+.2f})")
    else:
        print(f"{key}: {old} -> {new}")
