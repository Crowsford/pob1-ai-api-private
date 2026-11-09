
-- PoE BuildLab AI - Rare Item Evaluator v1
-- Validate first, calculate second.
-- Scope: ordinary Staff, one modifier replacement.
-- Read-only: no XML or equipment writes.

package.path =
    "../runtime/lua/?.lua;../runtime/lua/?/init.lua;"
    .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local json = require("dkjson")
local validator = dofile("rare_affix_validator_v3.lua")

local function readFile(path)
    local f, err = io.open(path, "rb")
    assert(f, err)
    local content = f:read("*a")
    f:close()
    return content
end

local function extractMods(raw)
    local lines = {}
    for line in raw:gmatch("[^\r\n]+") do
        lines[#lines + 1] = line
    end

    local startIndex, implicitCount

    for i, line in ipairs(lines) do
        local n = line:match("^Implicits:%s*(%d+)")
        if n then
            startIndex = i + 1
            implicitCount = tonumber(n)
            break
        end
    end

    assert(startIndex, "Implicits header missing")

    local mods = {}

    for i = startIndex + implicitCount, #lines do
        local line = lines[i]

        if line == "Fractured Item"
            or line == "Corrupted"
            or line == "Mirrored" then
            break
        end

        local crafted =
            line:find("{crafted}", 1, true) ~= nil
        local fractured =
            line:find("{fractured}", 1, true) ~= nil

        line = line:gsub("^%{crafted%}", "")
        line = line:gsub("^%{fractured%}", "")

        mods[#mods + 1] = {
            text = line,
            crafted = crafted,
            fractured = fractured
        }
    end

    return mods
end

local function validateRaw(raw)
    local levelText =
        raw:match("Item Level:%s*(%d+)")

    assert(levelText, "Item level missing")

    return validator.validate({
        baseCategory = "staff",
        itemLevel = tonumber(levelText),
        mods = extractMods(raw)
    })
end

local function replaceOnce(raw, oldText, newText)
    local startPos, endPos =
        raw:find(oldText, 1, true)

    assert(startPos, "Original modifier not found")

    assert(
        not raw:find(oldText, endPos + 1, true),
        "Modifier appears more than once"
    )

    return raw:sub(1, startPos - 1)
        .. newText
        .. raw:sub(endPos + 1)
end

local function metricPair(before, after)
    assert(type(before) == "number")
    assert(type(after) == "number")

    return {
        before = before,
        after = after,
        delta = after - before,
        percent = before ~= 0
            and (after - before) / before * 100
            or json.null
    }
end

local function run()
    local xmlPath = assert(arg[1], "Build XML required")
    local groupIndex = tonumber(arg[2] or "6")

    local oldMod = arg[3]
        or "+43% to Chaos Damage over Time Multiplier"

    local newMod = arg[4]
        or "+44% to Chaos Damage over Time Multiplier"

    assert(oldMod ~= newMod, "No change requested")

    dofile("HeadlessWrapper.lua")

    loadBuildFromXML(
        readFile(xmlPath),
        "Rare Item Evaluator"
    )

    local itemsTab = assert(build.itemsTab)
    local slot = assert(itemsTab.slots["Weapon 1"])
    local original = assert(itemsTab.items[slot.selItemId])

    assert(original.rarity == "RARE")
    assert(original.base.type == "Staff")

    local group =
        assert(build.skillsTab.socketGroupList[groupIndex])

    assert(group.enabled and group.slotEnabled)
    assert(group.gemList and #group.gemList > 0)

    build.mainSocketGroup = groupIndex

    wipeGlobalCache()
    build.outputRevision = build.outputRevision + 1
    build.buildFlag = false

    build.skillsTab:UpdateSocketGroups()
    build.calcsTab:BuildOutput()

    assert(build.mainSocketGroup == groupIndex)

    local raw = original:BuildRaw()
    local modifiedRaw = replaceOnce(raw, oldMod, newMod)

    -- Validate both item definitions BEFORE calculations.
    local originalValidation = validateRaw(raw)
    local candidateValidation = validateRaw(modifiedRaw)

    assert(
        originalValidation.status == "BASIC_CHECKS_PASSED",
        "Original item failed basic validation: "
            .. json.encode(originalValidation.errors)
    )

    assert(
        candidateValidation.status == "BASIC_CHECKS_PASSED",
        "Candidate rejected: "
            .. json.encode(candidateValidation.errors)
    )

    -- Only now calculate PoB metrics.
    local calcFunc, calcBase =
        build.calcsTab:GetMiscCalculator()

    assert(type(calcFunc) == "function")

    local baseline = calcBase or calcFunc({})

    -- NO-OP control.
    local unchanged = new("Item", raw)
    assert(unchanged.base)
    unchanged:BuildModList()

    local control = calcFunc({
        repSlotName = "Weapon 1",
        repItem = unchanged
    })

    local candidate = new("Item", modifiedRaw)
    assert(candidate.base)
    assert(candidate.rarity == "RARE")
    assert(candidate.base.type == original.base.type)

    candidate:BuildModList()

    local modified = calcFunc({
        repSlotName = "Weapon 1",
        repItem = candidate
    })

    -- Find every changed numeric PoB output.
    local differences = {}
    local seen = {}

    for key in pairs(baseline) do
        seen[key] = true
    end

    for key in pairs(modified) do
        seen[key] = true
    end

    for key in pairs(seen) do
        local before = baseline[key]
        local after = modified[key]

        if type(key) == "string"
            and type(before) == "number"
            and type(after) == "number"
            and before == before
            and after == after
            and math.abs(after - before) > 0.000001 then

            differences[#differences + 1] = {
                stat = key,
                before = before,
                after = after,
                delta = after - before
            }
        end
    end

    table.sort(differences, function(a, b)
        return a.stat < b.stat
    end)

    print("STAT_DIFF_JSON:" .. json.encode(differences))

    local keys = {
        "CombinedDPS",
        "TotalDot",
        "TotalEHP",
        "EnergyShield",
        "PhysicalMaximumHitTaken"
    }

    local metrics = {}
    local mismatches = 0

    for _, key in ipairs(keys) do
        local before = baseline[key]
        local noOp = control[key]
        local after = modified[key]

        assert(type(before) == "number",
            "Missing baseline stat: " .. key)
        assert(type(noOp) == "number",
            "Missing NO-OP stat: " .. key)
        assert(type(after) == "number",
            "Missing candidate stat: " .. key)

        local tolerance =
            0.000001 * math.max(1, math.abs(before))

        if math.abs(before - noOp) > tolerance then
            mismatches = mismatches + 1
        end

        metrics[key] = metricPair(before, after)
    end

    assert(mismatches == 0, "NO_OP_FAILED")

    assert(
        itemsTab.items[slot.selItemId] == original,
        "Original equipment changed"
    )

    local result = {
        schemaVersion = 1,
        status = "CALCULATED",
        slot = "Weapon 1",
        skillGroup = groupIndex,
        skillId = group.gemList[1].skillId,
        originalItem = original.name,

        change = {
            before = oldMod,
            after = newMod
        },

        validation = {
            original = originalValidation,
            candidate = candidateValidation
        },

        calculation = {
            noOpPassed = true,
            metrics = metrics
        },

        sourceXMLWritten = false,
        craftingVerified = false,
        acquisitionVerified = false,
        automaticApproval = false
    }

    print("RARE_EVALUATION_JSON:" .. json.encode(result))
end

local ok, err = pcall(run)

if not ok then
    io.stderr:write(
        "RARE_EVALUATION_ERROR:"
        .. tostring(err) .. "\n"
    )
    os.exit(1)
end
