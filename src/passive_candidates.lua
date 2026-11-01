
package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local path = assert(arg[1], "XML path required")

dofile("HeadlessWrapper.lua")

local file = assert(io.open(path, "rb"))
local xml = file:read("*a")
file:close()

loadBuildFromXML(xml, "Passive Candidates Test")

assert(main.mode == "BUILD", "Build not loaded")

local spec = build.spec
local usedBefore = spec:CountAllocNodes()

print("Class:", spec.curClassName)
print("Level:", build.characterLevel)
print("Passive points used:", usedBefore)
print("=== CANDIDATE NODES ===")

local candidates = {}

for id, node in pairs(spec.nodes) do
    if not node.alloc
        and node.path
        and node.type == "Normal"
        and not node.ascendancyName
        and not node.isMultipleChoiceOption
        and #node.intuitiveLeapLikesAffecting == 0 then

        local cost = 0
        for _, pathNode in ipairs(node.path) do
            if not pathNode.alloc
                and pathNode.type ~= "ClassStart"
                and pathNode.type ~= "AscendClassStart" then
                cost = cost + 1
            end
        end

        if cost == 1 then
            candidates[#candidates + 1] = {
                id = id,
                name = node.dn or node.name or "Unknown",
                cost = cost
            }
        end
    end
end

table.sort(candidates, function(a, b)
    return tonumber(a.id) < tonumber(b.id)
end)

print("One-point candidates:", #candidates)

for i = 1, math.min(15, #candidates) do
    local node = candidates[i]
    print(node.id, node.name, "Cost:", node.cost)
end


local json = require("dkjson")

print("RESULT_JSON:" .. json.encode({
    ok = true,
    className = spec.curClassName,
    level = build.characterLevel,
    pointsUsed = usedBefore,
    candidateCount = #candidates,
    candidates = candidates
}))
