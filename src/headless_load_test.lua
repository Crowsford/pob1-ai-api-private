package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

dofile("HeadlessWrapper.lua")

local path = os.getenv("USERPROFILE")
    .. "\\Documents\\Path of Building\\Builds\\BabaBan.xml"

local file, err = io.open(path, "rb")
assert(file, err)

local xml = file:read("*a")
file:close()

print("Loading BabaBan...")
loadBuildFromXML(xml, "BabaBan Headless Test")

assert(build and build.spec, "Build not initialized")
assert(build.calcsTab, "CalcsTab not initialized")

print("=== BUILD DIAGNOSTICS ===")
print("Build name:", build.buildName)
print("Build level:", build.characterLevel)
print("Class:", build.spec.curClassName)
print("Ascendancy:", build.spec.curAscendClassName)
print("Main output exists:", build.calcsTab.mainOutput ~= nil)
print("Current mode:", main and main.mode)

if not build.calcsTab.mainOutput then
    print("Trying one additional OnFrame...")
    runCallback("OnFrame")
end

print("Main output after frame:", build.calcsTab.mainOutput ~= nil)

local output = assert(build.calcsTab.mainOutput, "No calculation output")

print("=== HEADLESS BUILD LOADED ===")
print("Name:", build.buildName)
print("Class:", build.spec.curClassName)
print("Ascendancy:", build.spec.curAscendClassName)
print("Level:", build.characterLevel)
print("Life:", output.Life)
print("Mana:", output.Mana)
print("Total DPS:", output.TotalDPS)
print("Full DPS:", output.FullDPS)
print("Total EHP:", output.TotalEHP)
print("=== DAMAGE DIAGNOSTICS ===")

local output = build.calcsTab.mainOutput
local env = build.calcsTab.mainEnv

print("Main skill group:", tostring(build.mainSocketGroup))
print("Main skill exists:", tostring(env and env.player and env.player.mainSkill ~= nil))

local damageKeys = {
    "TotalDPS",
    "FullDPS",
    "CombinedDPS",
    "TotalDotDPS",
    "TotalDot",
    "DotDPS",
    "AverageDamage",
    "Speed",
}

for _, key in ipairs(damageKeys) do
    print(key .. ":", tostring(output[key]))
end

if env and env.player and env.player.mainSkill then
    local skill = env.player.mainSkill
    print("Skill name:", tostring(skill.name))
    print("Skill disabled:", tostring(skill.skillFlags and skill.skillFlags.disable))
    print("Disable reason:", tostring(skill.disableReason))
end