
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
local passiveExperiment = nil

if arg[3] then
    local nodeId = tonumber(arg[3])
    assert(nodeId and nodeId == math.floor(nodeId), "Invalid node ID")

    local spec = assert(build.spec, "Passive tree unavailable")
    local node = assert(spec.nodes[nodeId], "Passive node not found")

    assert(not node.alloc, "Node is already allocated")
    assert(node.type == "Normal", "Only normal passive nodes are supported")
    assert(node.path, "Node has no valid path")
    assert(
        node.type ~= "Mastery"
        and node.type ~= "ClassStart"
        and node.type ~= "AscendClassStart"
        and not node.ascendancyName
        and not node.isMultipleChoiceOption
        and #node.intuitiveLeapLikesAffecting == 0,
        "Unsupported passive node type"
    )

    local usedBefore, ascendBefore = spec:CountAllocNodes()

    local pathCost = 0
    for _, pathNode in ipairs(node.path) do
        if not pathNode.alloc then
            pathCost = pathCost + 1
        end
    end

    assert(pathCost == 1, "Only one-point paths are supported")

    spec:AllocNode(node)

    local usedAfter, ascendAfter = spec:CountAllocNodes()

    assert(node.alloc, "Node allocation failed")
    assert(usedAfter - usedBefore == 1, "Unexpected passive point cost")
    assert(ascendAfter == ascendBefore, "Ascendancy points changed")


    -- Recalculate using the same core sequence as PoB's Build mode.
    build.buildFlag = true

    wipeGlobalCache()

    build.outputRevision = build.outputRevision + 1
    build.buildFlag = false

    build.skillsTab:UpdateSocketGroups()
    build.calcsTab:BuildOutput()


    passiveExperiment = {
        nodeId = nodeId,
        nodeName = node.dn or node.name or "Unknown",
        pointsBefore = usedBefore,
        pointsAfter = usedAfter,
        pointsSpent = usedAfter - usedBefore,
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
