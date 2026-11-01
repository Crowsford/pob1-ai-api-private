
-- PoE BuildLab: Headless Evaluation v0.1
package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local json = require("dkjson")

local function emit(data)
    print("RESULT_JSON:" .. json.encode(data))
end

local function calculate()
    local xmlPath = arg[1]
    assert(xmlPath and xmlPath ~= "", "XML file path is required")

    local file, err = io.open(xmlPath, "rb")
    assert(file, err)

    local xml = file:read("*a")
    file:close()

    -- Initialize PoB calculation engine
    dofile("HeadlessWrapper.lua")

    -- Load build from XML
    loadBuildFromXML(xml, "BuildLab Evaluation")

-- Optional experiment: change character level
local newLevel = tonumber(arg[2])

if arg[2] and arg[2] ~= "" then
    assert(
        newLevel and newLevel >= 1 and newLevel <= 100
        and newLevel == math.floor(newLevel),
        "Level must be an integer between 1 and 100"
    )

    build.characterLevel = newLevel
    build.characterLevelAutoMode = false

    -- Recalculate after changing the level
    build.calcsTab:BuildOutput()
end

    assert(main.mode == "BUILD", "Build did not enter BUILD mode")


-- Optional experiment: allocate one passive node










-- Passive experiment: one or multiple comma-separated node IDs
local passiveExperiment = nil

if arg[3] and arg[3] ~= "" then
    local spec = assert(build.spec, "Passive tree unavailable")

    local requestedIds = {}
    local seen = {}

    for rawId in tostring(arg[3]):gmatch("[^,]+") do
        local nodeId = tonumber(rawId)

        assert(
            nodeId and nodeId > 0
            and nodeId == math.floor(nodeId),
            "Invalid passive node ID: " .. rawId
        )

        assert(not seen[nodeId], "Duplicate passive node ID")
        seen[nodeId] = true
        requestedIds[#requestedIds + 1] = nodeId
    end

    assert(#requestedIds > 0, "No passive nodes provided")
    assert(#requestedIds <= 10, "Maximum 10 nodes per experiment")

    local usedBefore, ascendBefore, secondaryBefore =
        spec:CountAllocNodes()

    local allocated = {}

    for _, nodeId in ipairs(requestedIds) do
        local node = assert(
            spec.nodes[nodeId],
            "Passive node not found: " .. nodeId
        )

        assert(not node.alloc, "Node already allocated: " .. nodeId)
        assert(node.type == "Normal", "Only normal nodes supported")
        assert(node.path, "No valid path to node: " .. nodeId)
        assert(not node.ascendancyName, "Ascendancy node unsupported")
        assert(not node.isMultipleChoiceOption, "Choice node unsupported")
        assert(
            #node.intuitiveLeapLikesAffecting == 0,
            "Special allocation mechanics unsupported"
        )

        local pathCost = 0

        for _, pathNode in ipairs(node.path) do
            if not pathNode.alloc then
                pathCost = pathCost + 1
            end
        end

        assert(
            pathCost == 1,
            "Node requires more than one point: " .. nodeId
        )

        spec:AllocNode(node)

        allocated[#allocated + 1] = {
            nodeId = nodeId,
            nodeName = node.dn or node.name or "Unknown"
        }
    end

    local usedAfter, ascendAfter, secondaryAfter =
        spec:CountAllocNodes()

    local pointsSpent = usedAfter - usedBefore

    assert(
        pointsSpent == #requestedIds,
        "Unexpected total passive point cost"
    )
    assert(ascendAfter == ascendBefore, "Ascendancy points changed")
    assert(
        secondaryAfter == secondaryBefore,
        "Secondary ascendancy points changed"
    )

    -- Reproduce PoB's core recalculation sequence
    build.buildFlag = true
    wipeGlobalCache()
    build.outputRevision = build.outputRevision + 1
    build.buildFlag = false
    build.skillsTab:UpdateSocketGroups()
    build.calcsTab:BuildOutput()

    passiveExperiment = {
        nodes = allocated,
        pointsBefore = usedBefore,
        pointsAfter = usedAfter,
        pointsSpent = pointsSpent,
        theoretical = true
    }
end











    local calcsTab = assert(build.calcsTab, "CalcsTab unavailable")
    local output = assert(calcsTab.mainOutput, "Calculation output unavailable")

    local function number(key)
        local value = tonumber(output[key])

        if value and value == value
            and value ~= math.huge
            and value ~= -math.huge then
            return value
        end

        return json.null
    end

    return {
        ok = true,
        engine = "Path of Building Headless",
        className = build.spec.curClassName,
        ascendClassName = build.spec.curAscendClassName,
        level = build.characterLevel,
        passiveExperiment = passiveExperiment or json.null,

stats = {
    -- Damage
    totalDPS = number("TotalDPS"),
    combinedDPS = number("CombinedDPS"),
    totalDotDPS = number("TotalDotDPS"),
    fullDPS = number("FullDPS"),

    -- Skill performance
    speed = number("Speed"),
    critChance = number("CritChance"),
    critMultiplier = number("CritMultiplier"),

    -- Resources
    life = number("Life"),
    lifeUnreserved = number("LifeUnreserved"),
    mana = number("Mana"),
    manaUnreserved = number("ManaUnreserved"),
    energyShield = number("EnergyShield"),

    -- Recovery
    lifeRegen = number("LifeRegen"),
    manaRegen = number("ManaRegen"),
    energyShieldRegen = number("EnergyShieldRegen"),
    energyShieldRecharge = number("EnergyShieldRecharge"),

    -- Defenses
    totalEHP = number("TotalEHP"),
    armour = number("Armour"),
    evasion = number("Evasion"),

    -- Elemental and chaos resistances
    fireResist = number("FireResist"),
    coldResist = number("ColdResist"),
    lightningResist = number("LightningResist"),
    chaosResist = number("ChaosResist"),

    -- Movement
    movementSpeedMod = number("MovementSpeedMod")
}

    }
end

local ok, result = xpcall(calculate, debug.traceback)

if ok then
    emit(result)
else
    emit({
        ok = false,
        error = tostring(result)
    })
    os.exit(1)
end
