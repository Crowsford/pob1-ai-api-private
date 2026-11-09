
import os
from experiment_runner import evaluate

result = evaluate(os.environ["BUILD_XML"], skill_group=6)
stats = result["stats"]

print("=== CORRECTED BASELINE ===")
print("Level:", result["level"])
print("Passive points:", result["passivePointsUsed"])
print("Skill group:", 6)
print("DPS:", stats["combinedDPS"])
print("EHP:", stats["totalEHP"])
print("Energy Shield:", stats["energyShield"])
print("Attack Block:", stats["blockChance"])
print("Spell Block:", stats["spellBlockChance"])
print("Mana:", stats["manaUnreserved"])
print("Mana Regen:", stats["manaRegen"])

validation = result.get("validation", {})
print("\n=== VALIDATION ===")
print("Attributes met:", validation.get("attributeRequirementsMet"))
print("Problems:", validation.get("problems"))
print("Special requirements:", validation.get("specialRequirements"))
