
-- PoE BuildLab AI — Headless Item Swap v0.1
-- Temporary item comparison using native PoB calculator.
-- Does NOT write to XML or change the saved build.

package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local json = require("dkjson")

local function readFile(path)
    local f, err = io.open(path, "rb")
    assert(f, err)
    local content = f:read("*a")
    f:close()
    return content
end

local function findUnique(name)
    for _, definitions in pairs(data.uniques or {}) do
        if type(definitions) == "table" then
            for _, raw in pairs(definitions) do
                if type(raw) == "string" then
                    local candidate = raw:match("^%s*([^\r\n]+)")

                    if candidate == name then
                        local item = new("Item", raw, "UNIQUE", true)
                        assert(item and item.base,
                            "Unique item could not be parsed")
                        return item
                    end
                end
            end
        end
    end

    error("Unique not found: " .. name)
end

local function selectCurrent(item)
    local variants = item.variantList

    if variants and #variants > 0 then
        local selected = nil

        for index, name in ipairs(variants) do
            if name == "Current" then
                assert(not selected, "Duplicate Current variant")
                selected = index
            end
        end

        assert(selected, "Current variant unavailable")
        item.variant = selected

        if type(item.NormaliseVariantSelections) == "function" then
            item:NormaliseVariantSelections()
        end
    end

    assert(not item.usesVariantGroups,
        "Variant groups not yet supported")

    assert(not item.versionList or #item.versionList == 0,
        "Additional version mechanism not yet supported")

    item:BuildModList()

    return variants and #variants > 0
        and variants[item.variant]
        or "Single"
end

local statNames = {
    "FullDPS",
    "TotalDPS",
    "CombinedDPS",
    "TotalDot",
    "Life",
    "EnergyShield",
    "Armour",
    "Evasion",
    "TotalEHP",
    "PhysicalMaximumHitTaken",
    "FireMaximumHitTaken",
    "ColdMaximumHitTaken",
    "LightningMaximumHitTaken",
    "ChaosMaximumHitTaken",
    "FireResist",
    "ColdResist",
    "LightningResist",
    "ChaosResist",
}

local function numericStats(output)
    assert(type(output) == "table",
        "Calculator did not return an output table")

    local stats = {}

    for _, key in ipairs(statNames) do
        local value = output[key]
        if type(value) == "number"
            and value == value
            and value ~= math.huge
            and value ~= -math.huge then
            stats[key] = value
        end
    end

    return stats
end

local function compare(before, after)
    local result = {}

    for _, key in ipairs(statNames) do
        local a = before[key]
        local b = after[key]

        if a ~= nil and b ~= nil then
            local change = b - a
            result[key] = {
                before = a,
                after = b,
                delta = change,
                percent = a ~= 0
                    and (change / math.abs(a) * 100)
                    or json.null,
            }
        end
    end

    return result
end

local function run()
    local xmlPath = assert(arg[1], "XML path required")
    local slotName = arg[2] or "Weapon 1"
    local uniqueName = arg[3] or "Breath of the Council"

    assert(slotName == "Weapon 1",
        "v0.1 currently permits Weapon 1 only")

    local originalXML = readFile(xmlPath)

    dofile("HeadlessWrapper.lua")
    loadBuildFromXML(originalXML, "BuildLab Item Swap Test")

    assert(build and main.mode == "BUILD",
        "Build not loaded")


    -- Select the six-gem body armour group for this test.
    local selectedGroup = 6
    local group = assert(
        build.skillsTab.socketGroupList[selectedGroup],
        "Skill group 6 not found"
    )

    assert(group.enabled and group.slotEnabled,
        "Skill group 6 is inactive")
    assert(group.slot == "Body Armour",
        "Skill group 6 is not in Body Armour")

    print("=== SELECTED SKILL GROUP ===")
    print("Group:", selectedGroup)
    print("Slot:", group.slot)
    print("Gems:", #(group.gemList or {}))

    for i, gem in ipairs(group.gemList or {}) do
        print("Gem", i,
            "| skillId:", tostring(gem.skillId),
            "| name:", tostring(gem.name))
    end

    build.mainSocketGroup = selectedGroup

    wipeGlobalCache()
    build.outputRevision = build.outputRevision + 1
    build.buildFlag = false
    build.skillsTab:UpdateSocketGroups()
    build.calcsTab:BuildOutput()

    assert(build.mainSocketGroup == selectedGroup,
        "Main skill group selection failed")

    local itemsTab = assert(build.itemsTab, "Items tab unavailable")
    local slot = assert(itemsTab.slots[slotName],
        "Requested slot not found")

    local originalItemId = slot.selItemId
    local originalItem = itemsTab.items[originalItemId]

    local candidate = findUnique(uniqueName)
    local selectedVariant = selectCurrent(candidate)

    local calcFunc, calcBase =
        build.calcsTab:GetMiscCalculator()

    assert(type(calcFunc) == "function",
        "Misc calculator is unavailable")

    -- Capture baseline returned by the same calculator.
    local baselineOutput = calcBase
    if type(baselineOutput) ~= "table" then
        baselineOutput = calcFunc({})
    end

    local before = numericStats(baselineOutput)

    -- NO_OP_VALIDATION: replacing an item with itself
    -- must reproduce the baseline within numerical tolerance.
    assert(originalItem, "Weapon 1 has no equipped item")

    local sameOutput = calcFunc({
        repSlotName = slotName,
        repItem = originalItem,
    })
    local sameStats = numericStats(sameOutput)

    local mismatches = {}
    for _, key in ipairs(statNames) do
        local a = before[key]
        local b = sameStats[key]

        if a ~= nil and b ~= nil then
            local tolerance = 0.000001 * math.max(1, math.abs(a))
            if math.abs(a - b) > tolerance then
                table.insert(mismatches,
                    string.format("%s: %.6f vs %.6f", key, a, b))
            end
        elseif a ~= b then
            table.insert(mismatches, key .. ": missing value")
        end
    end

    print("=== NO_OP_VALIDATION ===")
    print("Original weapon type:",
        originalItem.base and originalItem.base.type or "UNKNOWN")
    print("Candidate weapon type:",
        candidate.base and candidate.base.type or "UNKNOWN")
    print("Baseline comparison mismatches:", #mismatches)

    for _, mismatch in ipairs(mismatches) do
        print("MISMATCH:", mismatch)
    end

    assert(#mismatches == 0,
        "NO_OP_FAILED: original weapon substitution changed stats")


    -- Native PoB virtual item replacement.
    local replacementOutput = calcFunc({
        repSlotName = slotName,
        repItem = candidate,
    })

    local after = numericStats(replacementOutput)

    print("=== POST-SWAP REQUIREMENTS ===")

    local requirements = candidate.requirements or {}
    local attributes = {
        { "Level", build.characterLevel, requirements.level or 0 },
        { "Str", replacementOutput.Str, requirements.str or 0 },
        { "Dex", replacementOutput.Dex, requirements.dex or 0 },
        { "Int", replacementOutput.Int, requirements.int or 0 },
    }

    local requirementsPassed = true
    local requirementsComplete = true

    for _, entry in ipairs(attributes) do
        local name, actual, required = unpack(entry)

        if type(actual) ~= "number" then
            print(name, "| value unavailable")
            requirementsComplete = false
        else
            local passed = actual >= required

            print(
                name,
                "| actual:", actual,
                "| required:", required,
                "| pass:", tostring(passed)
            )

            if not passed then
                requirementsPassed = false
            end
        end
    end

    print("Requirements data complete:",
        tostring(requirementsComplete))
    print("Requirements passed:",
        requirementsComplete and tostring(requirementsPassed)
        or "NOT_VERIFIED")

    local differences = compare(before, after)

    -- Verify no equipment mutation happened.
    assert(slot.selItemId == originalItemId,
        "Original equipped item ID changed")
    assert(itemsTab.items[originalItemId] == originalItem,
        "Original item object changed")

    local meaningfulChanges = 0
    for _, value in pairs(differences) do
        if math.abs(value.delta) > 0.000001 then
            meaningfulChanges = meaningfulChanges + 1
        end
    end

    local result = {
        status = "CALCULATED",
        build = "BuildLab Item Swap Test",
        requestedSlot = slotName,
        originalItemId = originalItemId or json.null,
        originalItemName = originalItem
            and originalItem.name or json.null,
        candidate = uniqueName,
        selectedVariant = selectedVariant,
        baseline = before,
        replacement = after,
        differences = differences,
        comparedStats = (function()
            local count = 0
            for _ in pairs(differences) do
                count = count + 1
            end
            return count
        end)(),
        changedStats = meaningfulChanges,
        calculationChanged = meaningfulChanges > 0,
        originalEquipmentPreserved = true,
        sourceXMLWritten = false,
        slotCompatibilityVerified = false,
        characterRequirementsVerified = false,
    }

    print("=== HEADLESS ITEM SWAP v0.1 ===")
    print("Slot:", slotName)
    print("Original item:",
        originalItem and originalItem.name or "<empty>")
    print("Candidate:", uniqueName)
    print("Variant:", selectedVariant)
    print("Compared numeric stats:", result.comparedStats)
    print("Changed numeric stats:", meaningfulChanges)

    for _, key in ipairs(statNames) do
        local entry = differences[key]
        if entry and math.abs(entry.delta) > 0.000001 then
            print(string.format(
                "%s: %.2f -> %.2f (delta %+.2f)",
                key, entry.before, entry.after, entry.delta
            ))
        end
    end

    print("Original equipment preserved: YES")
    print("Source XML written: NO")
    print("Slot compatibility verified: NO")
    print("Character requirements verified: NO")
    print("ITEM_SWAP_JSON:" .. json.encode(result))
end

local ok, err = xpcall(run, debug.traceback)

if not ok then
    print("ITEM_SWAP_ERROR:" .. tostring(err))
    os.exit(1)
end
