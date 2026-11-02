
-- PoE BuildLab: Inspect Skills v0.1

package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local xmlPath = assert(arg[1], "XML path required")

local file = assert(io.open(xmlPath, "rb"))
local xml = file:read("*a")
file:close()

dofile("HeadlessWrapper.lua")
loadBuildFromXML(xml, "Skill Inspection")

assert(main.mode == "BUILD", "Build not loaded")

print("=== BUILD SKILLS ===")
print("Character level:", build.characterLevel)
print("Main socket group:", build.mainSocketGroup)
print("Total socket groups:", #build.skillsTab.socketGroupList)

for index, group in ipairs(build.skillsTab.socketGroupList) do
    print("")
    print("GROUP:", index)
    print("Enabled:", tostring(group.enabled))
    print("Slot enabled:", tostring(group.slotEnabled))
    print("Slot:", tostring(group.slot))
    print("Main active skill:", tostring(group.mainActiveSkill))
    print("Main active skill calcs:", tostring(group.mainActiveSkillCalcs))

    for gemIndex, gem in ipairs(group.gemList or {}) do
        print(
            " GEM:", gemIndex,
            "Name:", tostring(gem.nameSpec or gem.name),
            "Enabled:", tostring(gem.enabled)
        )
    end
end


print("")
print("=== MAIN SKILL TEST ===")

build.mainSocketGroup = 6

wipeGlobalCache()
build.outputRevision = build.outputRevision + 1
build.buildFlag = false
build.skillsTab:UpdateSocketGroups()
build.calcsTab:BuildOutput()

local output = build.calcsTab.mainOutput

print("Selected group:", build.mainSocketGroup)
print("Combined DPS:", tostring(output.CombinedDPS))
print("Total DoT DPS:", tostring(output.TotalDotDPS))
print("Mana cost:", tostring(output.ManaCost))
print("Speed:", tostring(output.Speed))
print("Total EHP:", tostring(output.TotalEHP))
