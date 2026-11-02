
package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local xmlPath = assert(arg[1], "XML path required")
local nodeId = assert(tonumber(arg[2]), "Node ID required")

dofile("HeadlessWrapper.lua")

local file = assert(io.open(xmlPath, "rb"))
local xml = file:read("*a")
file:close()

loadBuildFromXML(xml, "Passive Inspection")

local node = assert(build.spec.nodes[nodeId], "Node not found")

print("ID:", node.id)
print("Name:", node.dn or node.name)
print("Type:", node.type)
print("Allocated:", tostring(node.alloc))

print("=== NODE STATS ===")
for _, stat in ipairs(node.sd or {}) do
    print(stat)
end

print("=== MODIFIERS ===")
if node.modList then
    for _, mod in ipairs(node.modList) do
        print(
            "name:", tostring(mod.name),
            "type:", tostring(mod.type),
            "value:", tostring(mod.value)
        )
    end
end

print("=== SELECTED SKILL ===")
local output = build.calcsTab.mainOutput
print("Speed:", tostring(output.Speed))
print("CombinedDPS:", tostring(output.CombinedDPS))
