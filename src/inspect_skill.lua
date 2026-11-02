
package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local xmlPath = assert(arg[1], "XML path required")

local file = assert(io.open(xmlPath, "rb"))
local xml = file:read("*a")
file:close()

dofile("HeadlessWrapper.lua")
loadBuildFromXML(xml, "Skill Inspection")

assert(main.mode == "BUILD", "Build not loaded")

print("=== SELECTED SOCKET GROUP ===")
print("Group index:", tostring(build.mainSocketGroup))

local group = build.skillsTab.socketGroupList[build.mainSocketGroup]

if group then
    print("Selected skill index:", tostring(group.mainActiveSkill))
    print("Socket group label:", tostring(group.label))
else
    print("No selected socket group")
end

print("=== CALCULATED MAIN SKILL ===")

local env = build.calcsTab.mainEnv
local actor = env and env.player
local skill = actor and actor.mainSkill

if skill then
    print("Skill name:", tostring(skill.name))
    print("Skill ID:", tostring(skill.skillId))

    print("=== SKILL FLAGS ===")
    for key, value in pairs(skill.skillFlags or {}) do
        if value then
            print(key, tostring(value))
        end
    end
else
    print("No calculated main skill")
end

print("=== CALCULATED OUTPUT ===")
local output = build.calcsTab.mainOutput
print("Speed:", tostring(output.Speed))
print("CombinedDPS:", tostring(output.CombinedDPS))
