
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


-- Find allocated nodes that appear to be removable
-- without disconnecting other allocated nodes.
local removalCandidates = {}

for id, node in pairs(spec.allocNodes) do
    if node.type == "Normal"
        and not node.ascendancyName
        and not node.isMultipleChoiceOption
        and node.depends
        and #node.depends == 1 then

        removalCandidates[#removalCandidates + 1] = {
            id = id,
            name = node.dn or node.name or "Unknown"
        }
    end
end

table.sort(removalCandidates, function(a, b)
    return tonumber(a.id) < tonumber(b.id)
end)

print("One-point removal candidates:", #removalCandidates)

for i = 1, math.min(15, #removalCandidates) do
    local node = removalCandidates[i]
    print("REMOVE:", node.id, node.name)
end


local json = require("dkjson")

print("RESULT_JSON:" .. json.encode({
    ok = true,
    className = spec.curClassName,
    level = build.characterLevel,
    pointsUsed = usedBefore,
    candidateCount = #candidates,
    candidates = candidates,
    removalCandidateCount = #removalCandidates,
    removalCandidates = removalCandidates
}))

print("=== DEPENDENCY TEST CANDIDATES ===")

local dependencyCandidates = {}

for id, node in pairs(spec.allocNodes) do
    if node.type == "Normal"
        and not node.ascendancyName
        and not node.isMultipleChoiceOption
        and node.depends
        and #node.depends > 1 then

        dependencyCandidates[#dependencyCandidates + 1] = {
            id = id,
            name = node.dn or node.name or "Unknown",
            count = #node.depends
        }
    end
end

table.sort(dependencyCandidates, function(a, b)
    return a.count > b.count
end)

for i = 1, math.min(10, #dependencyCandidates) do
    local node = dependencyCandidates[i]

    print(
        node.id,
        node.name,
        "Dependent nodes:",
        node.count
    )
end

print("=== DEPENDENCY CONFLICT DIAGNOSTIC ===")

local first = spec.allocNodes[7503]
local second = spec.allocNodes[22315]

assert(first, "Node 7503 is not allocated")
assert(second, "Node 22315 is not allocated")

local function showDependencies(node)
    print(
        "Node:",
        node.id,
        node.dn or node.name,
        "Depends count:",
        #node.depends,
        "Connected to start:",
        tostring(node.connectedToStart)
    )

    for _, dependent in ipairs(node.depends) do
        print(
            "  Dependent:",
            dependent.id,
            dependent.dn or dependent.name
        )
    end
end

showDependencies(first)
showDependencies(second)

print("=== SHARED LINKS ===")

local function allocatedNeighbors(node)
    local result = {}

    for _, other in ipairs(node.linked) do
        if other.alloc then
            result[other.id] = true
        end
    end

    return result
end

local a = allocatedNeighbors(first)
local b = allocatedNeighbors(second)

for id in pairs(a) do
    if b[id] then
        print("Shared allocated neighbor:", id)
    end
end

print("=== DISCONNECTED NODE DETAILS ===")

for _, id in ipairs({4432, 13753, 42795}) do
    local node = spec.nodes[id]

    if node then
        print(
            "ID:", id,
            "Name:", node.dn or node.name or "Unknown",
            "Type:", node.type or "Unknown",
            "Allocated:", tostring(node.alloc),
            "Linked nodes:", #node.linked
        )

        for _, linked in ipairs(node.linked) do
            if linked.alloc then
                print(
                    "  Allocated neighbor:",
                    linked.id,
                    linked.dn or linked.name or "Unknown"
                )
            end
        end
    else
        print("Node not found:", id)
    end
end

print("=== REPLACEMENT NODE CONNECTIONS ===")

for _, id in ipairs({55571, 63138}) do
    local node = spec.nodes[id]

    if node then
        print(
            "Node:", id,
            node.dn or node.name or "Unknown",
            "Allocated:", tostring(node.alloc)
        )

        for _, other in ipairs(node.linked) do
            print(
                "  Neighbor:", other.id,
                other.dn or other.name or "Unknown",
                "Allocated:", tostring(other.alloc)
            )
        end
    else
        print("Node not found:", id)
    end
end