
-- PoE BuildLab AI - Rare Affix Validator v2
-- Reads actual equipped item from XML.
-- Tests affix identification and basic combination rules.
-- Does NOT write to XML or PoB files.

package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local explicit = dofile("Data/ModExplicit.lua")
local master = dofile("Data/ModMaster.lua")

local function readFile(path)
    local f, err = io.open(path, "rb")
    assert(f, err)
    local content = f:read("*a")
    f:close()
    return content
end

local function cleanLine(line)
    local crafted = line:find("{crafted}", 1, true) ~= nil
    local fractured = line:find("{fractured}", 1, true) ~= nil

    line = line:gsub("^%{crafted%}", "")
    line = line:gsub("^%{fractured%}", "")

    return {
        text = line,
        crafted = crafted,
        fractured = fractured
    }
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

        mods[#mods + 1] = cleanLine(line)
    end

    return mods
end

local function matches(template, actual)
    if template == actual then return true end

    local low, high = template:match("%((%d+)%-(%d+)%)")
    if not low then return false end

    local value = actual:match("(%d+)")
    if not value then return false end

    value = tonumber(value)

    if value < tonumber(low) or value > tonumber(high) then
        return false
    end

    local normalized = template:gsub("%(%d+%-%d+%)", tostring(value))
    return normalized == actual
end

local function getStaffWeight(mod)
    for i, key in ipairs(mod.weightKey or {}) do
        if key == "staff" then
            return (mod.weightVal or {})[i] or 0
        end
    end
    return 0
end

local function identify(entry, itemLevel)
    local candidates = {}

    if entry.crafted then
        for i, mod in ipairs(master) do
            if mod.types and mod.types.Staff
                and (mod.level or 0) <= itemLevel
                and #mod == 1
                and matches(mod[1], entry.text) then

                candidates[#candidates + 1] = {
                    id = "Master #" .. i,
                    mod = mod,
                    source = "CRAFTED"
                }
            end
        end
    else
        for id, mod in pairs(explicit) do
            if (mod.level or 0) <= itemLevel
                and getStaffWeight(mod) > 0
                and #mod == 1
                and matches(mod[1], entry.text) then

                candidates[#candidates + 1] = {
                    id = id,
                    mod = mod,
                    source = entry.fractured and "FRACTURED" or "NORMAL"
                }
            end
        end
    end

    table.sort(candidates, function(a, b)
        return a.id < b.id
    end)

    return candidates
end

local function validate(mods, itemLevel)
    local prefixes, suffixes = 0, 0
    local groups = {}
    local errors = {}

    for i, entry in ipairs(mods) do
        local candidates = identify(entry, itemLevel)

        print("\n[" .. i .. "] " .. entry.text)
        print("Candidates:", #candidates)

        if #candidates ~= 1 then
            errors[#errors + 1] =
                "AFFIX_UNRESOLVED: " .. entry.text
        else
            local c = candidates[1]
            local mod = c.mod

            print("ID:", c.id)
            print("Type:", mod.type)
            print("Group:", mod.group)
            print("Source:", c.source)

            if mod.type == "Prefix" then
                prefixes = prefixes + 1
            elseif mod.type == "Suffix" then
                suffixes = suffixes + 1
            else
                errors[#errors + 1] =
                    "UNKNOWN_AFFIX_TYPE: " .. c.id
            end

            if mod.group then
                if groups[mod.group] then
                    errors[#errors + 1] =
                        "GROUP_CONFLICT: " .. mod.group
                else
                    groups[mod.group] = true
                end
            end
        end
    end

    if prefixes > 3 then
        errors[#errors + 1] = "TOO_MANY_PREFIXES"
    end

    if suffixes > 3 then
        errors[#errors + 1] = "TOO_MANY_SUFFIXES"
    end

    print("\nPrefixes:", prefixes)
    print("Suffixes:", suffixes)

    for _, err in ipairs(errors) do
        print("ERROR:", err)
    end

    return {
        passed = #errors == 0,
        prefixes = prefixes,
        suffixes = suffixes,
        errors = errors
    }
end

local function hasError(result, code)
    for _, err in ipairs(result.errors) do
        if err:find(code, 1, true) then
            return true
        end
    end
    return false
end

local function run()
    local xmlPath = assert(arg[1], "Build XML required")

    dofile("HeadlessWrapper.lua")
    loadBuildFromXML(readFile(xmlPath), "Affix Validator v2")

    local itemsTab = assert(build.itemsTab)
    local slot = assert(itemsTab.slots["Weapon 1"])
    local original = assert(itemsTab.items[slot.selItemId])

    assert(original.rarity == "RARE")
    assert(original.base.type == "Staff")

    local raw = original:BuildRaw()
    local itemLevelText = raw:match("Item Level:%s*(%d+)")
        assert(itemLevelText, "Item level missing")
    local itemLevel = tonumber(itemLevelText)

    local mods = extractMods(raw)

    print("=== ORIGINAL ITEM ===")
    print("Name:", original.name)
    print("Item Level:", itemLevel)
    print("Explicit mods:", #mods)

    assert(#mods == 6, "Expected six explicit modifiers")

    print("\n=== POSITIVE TEST ===")
    local positive = validate(mods, itemLevel)
    assert(positive.passed, "POSITIVE_TEST_FAILED")
    assert(positive.prefixes == 3)
    assert(positive.suffixes == 3)

    print("Positive test: PASS")

    -- Synthetic test. The XML and equipped item stay unchanged.
    local invalid = {}
    for i, entry in ipairs(mods) do
        invalid[i] = entry
    end

    invalid[#invalid + 1] = {
        text = "+1 to Level of all Spell Skill Gems",
        crafted = false,
        fractured = false
    }

    print("\n=== NEGATIVE TEST ===")
    local negative = validate(invalid, itemLevel)

    assert(not negative.passed,
        "NEGATIVE_TEST_WAS_ACCEPTED")
    assert(hasError(negative, "TOO_MANY_PREFIXES"),
        "PREFIX_LIMIT_NOT_DETECTED")
    assert(hasError(negative, "GROUP_CONFLICT"),
        "GROUP_CONFLICT_NOT_DETECTED")

    print("Negative test: PASS")

    assert(itemsTab.items[slot.selItemId] == original,
        "Original equipment changed")


    -- NEGATIVE TEST 2: Value outside the allowed staff range.
    local invalidValue = {}
    for i, entry in ipairs(mods) do
        invalidValue[i] = {
            text = entry.text,
            crafted = entry.crafted,
            fractured = entry.fractured
        }
    end

    invalidValue[2].text =
        "+76% to Chaos Damage over Time Multiplier"

    print("\n=== NEGATIVE TEST: INVALID VALUE ===")
    local valueResult = validate(invalidValue, itemLevel)

    assert(not valueResult.passed,
        "INVALID_VALUE_WAS_ACCEPTED")
    assert(hasError(valueResult, "AFFIX_UNRESOLVED"),
        "INVALID_VALUE_NOT_DETECTED")

    print("Invalid value test: PASS")

    -- NEGATIVE TEST 3: Item level is too low.
    print("\n=== NEGATIVE TEST: LOW ITEM LEVEL ===")
    local levelResult = validate(mods, 1)

    assert(not levelResult.passed,
        "LOW_ITEM_LEVEL_WAS_ACCEPTED")
    assert(hasError(levelResult, "AFFIX_UNRESOLVED"),
        "LOW_ITEM_LEVEL_NOT_DETECTED")

    print("Low item level test: PASS")


    print("\n=== FINAL ===")
    print("Original item identification: PASS")
    print("Invalid combination rejected: PASS")
    print("Source XML written: NO")
    print("Crafting feasibility verified: NO")
    print("Result: PASS")
end

local ok, err = pcall(run)
if not ok then
    io.stderr:write("AFFIX_VALIDATOR_ERROR: "
        .. tostring(err) .. "\n")
    os.exit(1)
end
