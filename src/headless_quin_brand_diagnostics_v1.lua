
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
-- Optional fifth argument: main skill group
local skillGroupArg = arg[5]

if skillGroupArg and skillGroupArg ~= "" then
    local skillGroup = tonumber(skillGroupArg)

    assert(
        skillGroup
        and skillGroup == math.floor(skillGroup)
        and skillGroup >= 1
        and skillGroup <= #build.skillsTab.socketGroupList,
        "Invalid main skill group"
    )

    local group = build.skillsTab.socketGroupList[skillGroup]

    assert(group.enabled, "Selected skill group is disabled")
    assert(group.slotEnabled, "Selected skill slot is disabled")

    build.mainSocketGroup = skillGroup
    -- Recalculate after selecting the main skill group
    wipeGlobalCache()
    build.outputRevision = build.outputRevision + 1
    build.buildFlag = false
    build.skillsTab:UpdateSocketGroups()
    build.calcsTab:BuildOutput()
end


-- Optional experiment: allocate one passive node







-- Tree Integrity Guard v0.1
-- Snapshot the originally allocated passive nodes.

local originalAllocNodes = {}

do
    local spec = assert(build.spec, "Passive tree unavailable")

    for nodeId in pairs(spec.allocNodes) do
        originalAllocNodes[nodeId] = true
    end
end

local expectedRemovedNodes = {}
local expectedAddedNodes = {}

-- Capture removal IDs before modifying the tree.
-- Only singly removable normal passive nodes are supported.
local removalExperiment = nil

if arg[4] and arg[4] ~= "" then
    local spec = assert(build.spec, "Passive tree unavailable")
    local requestedIds = {}
    local seen = {}

    for rawId in tostring(arg[4]):gmatch("[^,]+") do
        local nodeId = tonumber(rawId)

        assert(
            nodeId and nodeId > 0
            and nodeId == math.floor(nodeId),
            "Invalid removal node ID: " .. rawId
        )

        assert(not seen[nodeId], "Duplicate removal node ID")
        seen[nodeId] = true
        requestedIds[#requestedIds + 1] = nodeId
        expectedRemovedNodes[nodeId] = true
    end

    assert(#requestedIds > 0, "No removal nodes provided")
    assert(#requestedIds <= 10, "Maximum 10 removals")

    local usedBefore, ascendBefore, secondaryBefore =
        spec:CountAllocNodes()

    local removed = {}

    for _, nodeId in ipairs(requestedIds) do
        local node = assert(
            spec.allocNodes[nodeId],
            "Node is not allocated: " .. nodeId
        )

        assert(node.type == "Normal", "Only normal nodes supported")
        assert(not node.ascendancyName, "Ascendancy removal unsupported")
        assert(not node.isMultipleChoiceOption, "Choice removal unsupported")

        local before = {}
        for id in pairs(spec.allocNodes) do
            before[id] = true
        end

        spec:DeallocNode(node)

        local disappeared = {}
        for id in pairs(before) do
            if not spec.allocNodes[id] then
                disappeared[#disappeared + 1] = id
            end
        end


        if #disappeared ~= 1 or disappeared[1] ~= nodeId then
            table.sort(disappeared)

            local unexpected = {}

            for _, id in ipairs(disappeared) do
                if id ~= nodeId then
                    unexpected[#unexpected + 1] = id
                end
            end

            error(
                "TREE_CONFLICT"
                .. "|requested=" .. tostring(nodeId)
                .. "|disconnected=" .. table.concat(unexpected, ",")
            )
        end


        removed[#removed + 1] = {
            nodeId = nodeId,
            nodeName = node.dn or node.name or "Unknown"
        }
    end

    local usedAfter, ascendAfter, secondaryAfter =
        spec:CountAllocNodes()

    assert(
        usedBefore - usedAfter == #requestedIds,
        "Unexpected passive point refund"
    )
    assert(ascendAfter == ascendBefore, "Ascendancy points changed")
    assert(
        secondaryAfter == secondaryBefore,
        "Secondary ascendancy points changed"
    )

    removalExperiment = {
        nodes = removed,
        pointsBefore = usedBefore,
        pointsAfter = usedAfter,
        pointsFreed = usedBefore - usedAfter
    }
end


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
        expectedAddedNodes[nodeId] = true
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
        assert(
            node.type == "Normal" or node.type == "Notable",
            "Only normal and notable nodes supported"
        )
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

-- Recalculate also when the experiment only removes nodes
if removalExperiment and not passiveExperiment then
    build.buildFlag = true
    wipeGlobalCache()
    build.outputRevision = build.outputRevision + 1
    build.buildFlag = false
    build.skillsTab:UpdateSocketGroups()
    build.calcsTab:BuildOutput()
end

-- Verify the exact final set of allocated passive nodes.
-- Expected = (original - removed) + added.

if removalExperiment or passiveExperiment then
    local spec = assert(build.spec, "Passive tree unavailable")
    local expected = {}

    for nodeId in pairs(originalAllocNodes) do
        if not expectedRemovedNodes[nodeId] then
            expected[nodeId] = true
        end
    end

    for nodeId in pairs(expectedAddedNodes) do
        assert(
            not expected[nodeId],
            "Unexpected duplicate allocation: " .. nodeId
        )
        expected[nodeId] = true
    end

    for nodeId in pairs(expected) do
        assert(
            spec.allocNodes[nodeId] ~= nil,
            "Tree integrity: expected node missing: " .. nodeId
        )
    end

    for nodeId in pairs(spec.allocNodes) do
        assert(
            expected[nodeId] == true,
            "Tree integrity: unexpected allocated node: " .. nodeId
        )
    end
end







    local calcsTab = assert(build.calcsTab, "CalcsTab unavailable")
    local output = assert(calcsTab.mainOutput, "Calculation output unavailable")
    local keys = {}
    for k, v in pairs(output) do if type(k) == "string" and type(v) == "number" and (k:lower():find("brand", 1, true) or k:lower():find("duration", 1, true) or k:lower():find("activ", 1, true) or k:lower():find("cast", 1, true) or k:lower():find("speed", 1, true) or k:lower():find("mana", 1, true) or k:lower():find("hit", 1, true)) then keys[#keys + 1] = k end end
    table.sort(keys)
    print("=== QUIN BRAND OUTPUT DIAGNOSTICS ===")
    for _, k in ipairs(keys) do print("POB_FIELD:", k, "=", output[k]) end

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
	extraPoints = tonumber(build.calcsTab.mainOutput.ExtraPoints) or 0,
	passivePointsUsed = select(1, build.spec:CountAllocNodes()),
        passiveExperiment = passiveExperiment or json.null,
	removalExperiment = removalExperiment or json.null,


validation = (function()
    local output = build.calcsTab.mainOutput

local specialRequirements = {
    omni = tonumber(output.Omni),
    reqOmni = tonumber(output.ReqOmni),
    reqStr = tonumber(output.ReqStr),
    reqDex = tonumber(output.ReqDex),
    reqInt = tonumber(output.ReqInt),
}

    local attributes = {
        str = tonumber(output.Str),
        dex = tonumber(output.Dex),
        int = tonumber(output.Int)
    }

    local requirements = {
        str = tonumber(output.ReqStr) or 0,
        dex = tonumber(output.ReqDex) or 0,
        int = tonumber(output.ReqInt) or 0
    }

    local problems = {}

    for attr, required in pairs(requirements) do
        local actual = attributes[attr]

        if actual == nil then
            problems[#problems + 1] =
                "Attribute unavailable: " .. attr
        elseif actual < required then
            problems[#problems + 1] =
                attr .. ": " .. actual ..
                " / required " .. required
        end
    end

    local strengthSource = output.ReqStrItem
    local sourceInfo = nil

    if strengthSource then
        sourceInfo = {
            type = strengthSource.source or "Unknown",
            name = strengthSource.source == "Gem"
                and strengthSource.sourceGem
                and strengthSource.sourceGem.nameSpec
                or strengthSource.source == "Item"
                and strengthSource.sourceItem
                and strengthSource.sourceItem.name
                or "Unknown"
        }
    end

    return {
        attributes = attributes,
        requirements = requirements,
        attributeRequirementsMet = #problems == 0,
        strengthRequirementSource = sourceInfo or json.null,
	specialRequirements = specialRequirements,
        problems = problems
    }
end)(),


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
    manaCost = number("ManaCost"),
    manaPerSecond = number("ManaPerSecond"),
    lifeCost = number("LifeCost"),
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
    movementSpeedMod = number("MovementSpeedMod"),

    blockChance = number("BlockChance"),
    spellBlockChance = number("SpellBlockChance"),
    blockChanceMax = number("BlockChanceMax"),
    spellBlockChanceMax = number("SpellBlockChanceMax"),
    spellSuppressionChance = number("SpellSuppressionChance"),
    effectiveSpellSuppressionChance = number("EffectiveSpellSuppressionChance"),
    spellSuppressionEffect = number("SpellSuppressionEffect"),
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
