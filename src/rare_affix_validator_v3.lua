
-- PoE BuildLab AI - Rare Affix Validator v3
-- Independent, read-only validation module.
-- Scope: ordinary Staff, single-line affixes.
-- Crafting/acquisition feasibility is NOT verified.

local M = {}

local explicit = dofile("Data/ModExplicit.lua")
local master = dofile("Data/ModMaster.lua")

local function matches(template, actual)
    if template == actual then
        return true
    end

    local low, high = template:match("%((%d+)%-(%d+)%)")
    if not low then return false end

    local count = 0
    for _ in template:gmatch("%(%d+%-%d+%)") do
        count = count + 1
    end

    -- Multiple numeric ranges are not supported yet.
    if count ~= 1 then return false end

    local value = actual:match("(%d+)")
    if not value then return false end
    value = tonumber(value)

    if value < tonumber(low) or value > tonumber(high) then
        return false
    end

    return template:gsub("%(%d+%-%d+%)", tostring(value)) == actual
end

local function staffWeight(mod)
    for i, key in ipairs(mod.weightKey or {}) do
        if key == "staff" then
            return (mod.weightVal or {})[i] or 0
        end
    end
    return 0
end

local function findCandidates(entry, itemLevel)
    local found = {}
    local textMatches = 0
    local baseMatches = 0

    if entry.crafted then
        for i, mod in ipairs(master) do
            if #mod == 1 and matches(mod[1], entry.text) then
                textMatches = textMatches + 1

                if mod.types and mod.types.Staff then
                    baseMatches = baseMatches + 1

                    if (mod.level or 0) <= itemLevel then
                        found[#found + 1] = {
                            id = "Master #" .. i,
                            type = mod.type,
                            group = mod.group,
                            source = "CRAFTED",
                            requiredLevel = mod.level
                        }
                    end
                end
            end
        end
    else
        for id, mod in pairs(explicit) do
            if #mod == 1 and matches(mod[1], entry.text) then
                textMatches = textMatches + 1

                if staffWeight(mod) > 0 then
                    baseMatches = baseMatches + 1

                    if (mod.level or 0) <= itemLevel then
                        found[#found + 1] = {
                            id = id,
                            type = mod.type,
                            group = mod.group,
                            source = entry.fractured
                                and "FRACTURED" or "NORMAL",
                            requiredLevel = mod.level
                        }
                    end
                end
            end
        end
    end

    table.sort(found, function(a, b)
        return a.id < b.id
    end)

    local reason = nil

    if #found > 1 then
        reason = "AMBIGUOUS_AFFIX"
    elseif #found == 0 then
        if textMatches == 0 then
            reason = "UNKNOWN_OR_OUT_OF_RANGE"
        elseif baseMatches == 0 then
            reason = "BASE_NOT_ALLOWED"
        else
            reason = "ITEM_LEVEL_TOO_LOW"
        end
    end

    return found, reason
end

function M.validate(spec)
    assert(type(spec) == "table", "Specification required")
    assert(spec.baseCategory == "staff",
        "Only ordinary Staff is supported")
    assert(type(spec.itemLevel) == "number"
        and spec.itemLevel >= 1
        and spec.itemLevel <= 100
        and spec.itemLevel % 1 == 0,
        "Invalid itemLevel")
    assert(type(spec.mods) == "table", "Mods required")

    local result = {
        schemaVersion = 3,
        status = "UNVERIFIED",
        baseCategory = spec.baseCategory,
        itemLevel = spec.itemLevel,
        prefixes = 0,
        suffixes = 0,
        mods = {},
        errors = {},
        craftingVerified = false,
        acquisitionVerified = false
    }

    local groups = {}
    local craftedCount = 0
    local fracturedCount = 0

    local function addError(code, index)
        result.errors[#result.errors + 1] = {
            code = code,
            modIndex = index
        }
    end

    for i, entry in ipairs(spec.mods) do
        assert(type(entry.text) == "string",
            "Mod text required at index " .. i)

        local candidates, reason =
            findCandidates(entry, spec.itemLevel)

        local record = {
            text = entry.text,
            crafted = entry.crafted == true,
            fractured = entry.fractured == true,
            candidates = candidates,
            status = reason or "MATCHED"
        }

        result.mods[#result.mods + 1] = record

        if entry.crafted then craftedCount = craftedCount + 1 end
        if entry.fractured then fracturedCount = fracturedCount + 1 end

        if entry.crafted and entry.fractured then
            addError("CONFLICTING_SOURCE_MARKERS", i)
        end

        if reason then
            addError(reason, i)
        else
            local mod = candidates[1]

            if mod.type == "Prefix" then
                result.prefixes = result.prefixes + 1
            elseif mod.type == "Suffix" then
                result.suffixes = result.suffixes + 1
            else
                addError("UNKNOWN_AFFIX_TYPE", i)
            end

            if mod.group then
                if groups[mod.group] then
                    addError("GROUP_CONFLICT", i)
                else
                    groups[mod.group] = true
                end
            end
        end
    end

    if result.prefixes > 3 then
        addError("TOO_MANY_PREFIXES")
    end

    if result.suffixes > 3 then
        addError("TOO_MANY_SUFFIXES")
    end

    if craftedCount > 1 then
        addError("MULTIPLE_CRAFTED_MODS_UNVERIFIED")
    end

    if fracturedCount > 1 then
        addError("MULTIPLE_FRACTURED_MODS_UNVERIFIED")
    end

    if #spec.mods > 6 then
        addError("TOO_MANY_EXPLICIT_MODS")
    end

    result.status = #result.errors == 0
        and "BASIC_CHECKS_PASSED" or "REJECTED"

    return result
end

return M
