
-- PoE BuildLab: Passive Removal Test v0.1

package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local xmlPath = assert(arg[1], "XML path required")
local targetId = tonumber(arg[2]) or 5296

local file = assert(io.open(xmlPath, "rb"))
local xml = file:read("*a")
file:close()

dofile("HeadlessWrapper.lua")
loadBuildFromXML(xml, "Passive Removal Test")

assert(main.mode == "BUILD", "Build not loaded")

local spec = build.spec
local node = assert(spec.allocNodes[targetId], "Node is not allocated")

local before = {}
for id in pairs(spec.allocNodes) do
    before[id] = true
end

local pointsBefore = select(1, spec:CountAllocNodes())

print("=== BEFORE ===")
print("Target:", targetId, node.dn or node.name)
print("Passive points:", pointsBefore)

spec:DeallocNode(node)

local pointsAfter = select(1, spec:CountAllocNodes())

print("=== AFTER ===")
print("Passive points:", pointsAfter)
print("Points freed:", pointsBefore - pointsAfter)

local removed = {}

for id in pairs(before) do
    if not spec.allocNodes[id] then
        removed[#removed + 1] = id
    end
end

table.sort(removed)

print("Removed nodes:", #removed)

for _, id in ipairs(removed) do
    local removedNode = spec.nodes[id]
    print("REMOVED:", id, removedNode and (removedNode.dn or removedNode.name))
end

print("Original XML unchanged")
