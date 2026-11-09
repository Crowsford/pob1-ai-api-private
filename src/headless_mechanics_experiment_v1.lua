-- PoE BuildLab AI: Mechanics Experiment v1
-- Virtual item modifications only.
-- No XML writes. No crafting or acquisition validation.

package.path =
    "../runtime/lua/?.lua;../runtime/lua/?/init.lua;"
    .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local json = require("dkjson")

local function readFile(path)
    local f, err = io.open(path, "rb")
    assert(f, err)
    local content = f:read("*a")
    f:close()
    return content
end

local function insertBefore(raw, anchor, modifier)
    local first, last = raw:find(anchor, 1, true)
    assert(first, "Anchor modifier not found")
    assert(
        not raw:find(anchor, last + 1, true),
        "Anchor modifier is not unique"
    )
    assert(
        not raw:find(modifier, 1, true),
        "Test modifier already exists"
    )

    return raw:sub(1, first - 1)
        .. modifier .. "\n"
        .. raw:sub(first)
end

local function numberOrNull(value)
    if type(value) == "number"
        and value == value
        and value ~= math.huge
        and value ~= -math.huge then
        return value
    end
    return json.null
end

local measurementKeys = {
    "CastRate",
    "HitSpeed",
    "HitTime",
    "Speed",
    "Time",
    "CombinedDPS",
    "TotalEHP",
    "SpellBlockChance",
    "EnergyShield"
}

local function capture(output)
    local result = {}
    for _, key in ipairs(measurementKeys) do
        result[key] = numberOrNull(output[key])
    end
    return result
end

local function closeEnough(a, b)
    if type(a) ~= "number" or type(b) ~= "number" then
        return a == b
    end

    local tolerance =
        0.000001 * math.max(1, math.abs(a))

    return math.abs(a - b) <= tolerance
end

local function run()
    local xmlPath = assert(arg[1], "Build XML required")
    local groupIndex = tonumber(arg[2] or "6")

    assert(
        groupIndex and groupIndex >= 1
        and groupIndex == math.floor(groupIndex),
        "Invalid group index"
    )

    dofile("HeadlessWrapper.lua")

    loadBuildFromXML(
        readFile(xmlPath),
        "Mechanics Experiment v1"
    )

    local group =
        assert(build.skillsTab.socketGroupList[groupIndex])

    assert(group.enabled and group.slotEnabled)
    assert(group.gemList and #group.gemList > 0)

    local selectedSkillId = group.gemList[1].skillId

    assert(
        selectedSkillId == "BladeVortex",
        "This experiment requires BladeVortex"
    )

    build.mainSocketGroup = groupIndex

    wipeGlobalCache()
    build.outputRevision = build.outputRevision + 1
    build.buildFlag = false
    build.skillsTab:UpdateSocketGroups()
    build.calcsTab:BuildOutput()

    local itemsTab = assert(build.itemsTab)
    local slot = assert(itemsTab.slots["Weapon 1"])
    local original = assert(itemsTab.items[slot.selItemId])

    local raw = original:BuildRaw()

    local calcFunc, calcBase =
        build.calcsTab:GetMiscCalculator()

    assert(type(calcFunc) == "function")

    local baseline = calcBase or calcFunc({})

    local unchanged = new("Item", raw)
    assert(unchanged.base)
    unchanged:BuildModList()

    local control = calcFunc({
        repSlotName = "Weapon 1",
        repItem = unchanged
    })

    for _, key in ipairs(measurementKeys) do
        if type(baseline[key]) == "number"
            and type(control[key]) == "number" then
            assert(
                closeEnough(baseline[key], control[key]),
                "NO_OP_FAILED: " .. key
            )
        end
    end

    local anchor = "+13% Chance to Block Spell Damage"

    local interventions = {
        {
            id = "attack_speed",
            modifier = "20% increased Attack Speed"
        },
        {
            id = "cast_speed",
            modifier = "20% increased Cast Speed"
        }
    }

    local results = {}

    for _, intervention in ipairs(interventions) do
        local modifiedRaw = insertBefore(
            raw,
            anchor,
            intervention.modifier
        )

        local candidate = new("Item", modifiedRaw)

        assert(candidate.base, "Candidate base missing")
        assert(
            candidate.base.type == original.base.type,
            "Item base changed"
        )

        candidate:BuildModList()

        local calculated = calcFunc({
            repSlotName = "Weapon 1",
            repItem = candidate
        })

        assert(type(calculated) == "table")

        results[intervention.id] = {
            modifier = intervention.modifier,
            measurements = capture(calculated)
        }
    end

    assert(
        itemsTab.items[slot.selItemId] == original,
        "Original equipment changed"
    )

    local result = {
        schemaVersion = 1,
        status = "CALCULATED",
        skillGroup = groupIndex,
        skillId = selectedSkillId,

        baseline = capture(baseline),
        noOp = capture(control),
        interventions = results,

        checks = {
            noOpPassed = true,
            originalEquipmentUnchanged = true
        },

        sourceXMLWritten = false,
        craftingVerified = false,
        acquisitionVerified = false,
        automaticApproval = false,
        virtualItemMayBeUncraftable = true
    }

    print(
        "MECHANICS_EXPERIMENT_JSON:"
        .. json.encode(result)
    )
end

local ok, err = pcall(run)

if not ok then
    io.stderr:write(
        "MECHANICS_EXPERIMENT_ERROR:"
        .. tostring(err) .. "\n"
    )
    os.exit(1)
end
