-- QUIN Intelligence Planner v1
-- Test-only greedy algorithm.
-- No changes to XML or PoB source data.

package.path =
    "../runtime/lua/?.lua;../runtime/lua/?/init.lua;"
    .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local xmlPath = assert(arg[1], "XML required")
local targetInt = 88
local maxPoints = 39

local function readFile(path)
    local f = assert(io.open(path, "rb"))
    local data = f:read("*a")
    f:close()
    return data
end

local function recalculate()
    build.buildFlag = true
    wipeGlobalCache()
    build.outputRevision = build.outputRevision + 1
    build.buildFlag = false
    build.skillsTab:UpdateSocketGroups()
    build.calcsTab:BuildOutput()
    return assert(build.calcsTab.mainOutput)
end

local function pathCost(node)
    if not node.path then return nil end

    local cost = 0
    for _, step in ipairs(node.path) do
        if not step.alloc then
            cost = cost + 1
        end
    end
    return cost
end

local function intelligenceGain(node)
    local total = 0
    for _, stat in ipairs(node.sd or {}) do
        local number = stat:match("^%+(%d+) to Intelligence$")
        if number then
            total = total + tonumber(number)
        end
    end
    return total
end

local function run()
    dofile("HeadlessWrapper.lua")
    loadBuildFromXML(readFile(xmlPath), "QUIN INT Planner")

    local spec = assert(build.spec)

    assert(spec.curClassName == "Templar")
    assert(spec.curAscendClassName == "Inquisitor")
    assert(spec.treeVersion == "3_29")
    assert(build.characterLevel == 40)

    local group = assert(build.skillsTab.socketGroupList[1])
    assert(group.gemList[1].skillId == "StormBrand")
    assert(group.gemList[1].level == 8)

    local output = recalculate()
    local initialInt = assert(tonumber(output.Int))
    local initialDPS = tonumber(output.CombinedDPS) or 0
    local initialLife = tonumber(output.Life) or 0

    local spent = spec:CountAllocNodes()
    assert(spent == 0, "Expected empty passive tree")

    print("=== QUIN INTELLIGENCE PLANNER V1 ===")
    print("Initial INT:", initialInt)
    print("Required INT:", targetInt)
    print("Point budget:", maxPoints)
    print("Initial DPS:", initialDPS)
    print("Initial Life:", initialLife)
    print("")

    local steps = {}

    for iteration = 1, maxPoints do
        if tonumber(output.Int) >= targetInt then break end

        local best = nil
        local bestCost = nil
        local bestGain = nil

        for id, node in pairs(spec.nodes) do
            if node.type == "Normal"
                and not node.alloc
                and not node.ascendancyName
                and not node.isMultipleChoiceOption then

                local gain = intelligenceGain(node)
                local cost = pathCost(node)

                if gain > 0 and cost and cost > 0
                    and spent + cost <= maxPoints then

                    local isBetter = false

                    if not best then
                        isBetter = true
                    elseif gain / cost > bestGain / bestCost then
                        isBetter = true
                    elseif gain / cost == bestGain / bestCost then
                        if cost < bestCost then
                            isBetter = true
                        elseif cost == bestCost and id < best.id then
                            isBetter = true
                        end
                    end

                    if isBetter then
                        best = node
                        bestCost = cost
                        bestGain = gain
                    end
                end
            end
        end

        if not best then
            print("NO MORE REACHABLE INT NODES WITHIN BUDGET")
            break
        end

        local before = spent
        local beforeInt = tonumber(output.Int)

        spec:AllocNode(best)
        spec:BuildAllDependsAndPaths()

        spent = spec:CountAllocNodes()

        assert(spent > before, "Allocation failed")
        assert(spent <= maxPoints, "Point budget exceeded")

        output = recalculate()

        steps[#steps + 1] = best.id

        print(
            "STEP:", iteration,
            "| TARGET NODE:", best.id,
            "| PATH COST:", spent - before,
            "| INT:", beforeInt, "->", output.Int,
            "| POINTS:", spent
        )
    end

    print("")
    print("=== FINAL CHARACTER ===")
    print("Class:", spec.curClassName)
    print("Ascendancy:", spec.curAscendClassName)
    print("Level:", build.characterLevel)
    print("Points allocated:", spent)
    print("Intelligence:", tostring(output.Int))
    print("Required Intelligence:", targetInt)
    print("Life:", tostring(output.Life))
    print("Mana:", tostring(output.Mana))
    print("Combined DPS:", tostring(output.CombinedDPS))
    print("Selected target nodes:", table.concat(steps, ","))

    local success = tonumber(output.Int) >= targetInt

    print("")
    print("INT REQUIREMENT:", success and "PASS" or "FAIL")
    print("POINT BUDGET:", spent <= maxPoints and "PASS" or "FAIL")
    print("ALGORITHM:", "GREEDY BASELINE")
    print("OPTIMALITY VERIFIED: NO")
    print("BUILD EXPORTED: NO")
    print("XML MODIFIED: NO")
end

local ok, err = pcall(run)
if not ok then
    io.stderr:write(
        "QUIN_INT_PLANNER_ERROR:" .. tostring(err) .. "\n"
    )
    os.exit(1)
end
