
package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local xmlPath = assert(arg[1], "XML path required")

local file = assert(io.open(xmlPath, "rb"))
local xml = file:read("*a")
file:close()

dofile("HeadlessWrapper.lua")
loadBuildFromXML(xml, "Passive Removal Inspection")

assert(main.mode == "BUILD", "Build not loaded")

local spec = build.spec
local candidates = {}

for id, node in pairs(spec.allocNodes) do
    if node.type == "Normal"
        and not node.ascendancyName
        and not node.isMultipleChoiceOption
        and node.depends then

        local dependencies = {}

        for _, dep in ipairs(node.depends) do
            if dep.alloc then
                dependencies[#dependencies + 1] = {
                    id = dep.id,
                    name = dep.dn or dep.name or "Unknown"
                }
            end
        end

        candidates[#candidates + 1] = {
            id = id,
            name = node.dn or node.name or "Unknown",
            dependencyCount = #dependencies,
            dependencies = dependencies
        }
    end
end

table.sort(candidates, function(a, b)
    if a.dependencyCount ~= b.dependencyCount then
        return a.dependencyCount < b.dependencyCount
    end
    return a.id < b.id
end)

print("=== PASSIVE REMOVAL CANDIDATES ===")
print("Class:", spec.curClassName)
print("Level:", build.characterLevel)
print("Total normal-node candidates:", #candidates)

for i = 1, math.min(30, #candidates) do
    local item = candidates[i]
    print(
        "ID:", item.id,
        "Name:", item.name,
        "Dependencies:", item.dependencyCount
    )
end
