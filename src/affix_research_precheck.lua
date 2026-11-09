-- PoE BuildLab AI - Affix Research Precheck v1
-- Scope: ordinary Global Spell Gem Level prefixes on Staff
-- Read-only: no PoB calculations, no XML modifications.

package.path =
    "../runtime/lua/?.lua;../runtime/lua/?/init.lua;"
    .. package.path

local json = require("dkjson")

local function readFile(path)
    local file, err = io.open(path, "rb")
    assert(file, err)
    local content = file:read("*a")
    file:close()
    return content
end

local function run()
    local specPath = arg[1] or "rare_affix_test.json"
    local index = tonumber(arg[2] or "2")

    assert(index and index >= 0 and index % 1 == 0,
        "Invalid zero-based modifier index")

    local spec, _, err = json.decode(readFile(specPath))
    assert(spec, err or "Invalid item JSON")

    assert(spec.baseCategory == "staff",
        "Only staff is supported")

    local itemLevel = assert(tonumber(spec.itemLevel))
    local selected = assert(spec.mods[index + 1],
        "Modifier index not found")

    local current = selected.text
    local currentValue = current:match(
        "^%+(%d+) to Level of all Spell Skill Gems$"
    )

    assert(currentValue,
        "Unsupported modifier family for precheck v1")

    currentValue = tonumber(currentValue)

    assert(not selected.crafted,
        "Crafted modifiers are not supported")
    assert(not selected.fractured,
        "Fractured modifiers are not supported")

    local mods = dofile("Data/ModExplicit.lua")
    local tiers = {}

    for id, mod in pairs(mods) do
        if id:match("^GlobalSpellGemsLevelTwoHand%d+$")
            and mod.type == "Prefix"
            and mod.group == "GlobalIncreaseSpellSkillGemLevel" then

            local value = tonumber(
                mod[1]:match(
                    "^%+(%d+) to Level of all Spell Skill Gems$"
                )
            )

            local weight = 0
            for i, key in ipairs(mod.weightKey or {}) do
                if key == "staff" then
                    weight = mod.weightVal[i] or 0
                end
            end

            if value and weight > 0 and mod.level <= itemLevel then
                tiers[#tiers + 1] = {
                    id = id,
                    value = value,
                    requiredLevel = mod.level,
                    staffWeight = weight
                }
            end
        end
    end

    assert(#tiers > 0, "No eligible staff tiers found")

    table.sort(tiers, function(a, b)
        return a.value < b.value
    end)

    local currentMatched = false
    for _, tier in ipairs(tiers) do
        if tier.value == currentValue then
            currentMatched = true
        end
    end

    assert(currentMatched,
        "Current modifier not found in eligible tiers")

    local maximum = tiers[#tiers].value
    local available = {}

    for _, tier in ipairs(tiers) do
        if tier.value > currentValue then
            available[#available + 1] = tier
        end
    end

    local hasUpgrade = #available > 0

    local result = {
        schemaVersion = 1,
        status = hasUpgrade
            and "UPGRADE_AVAILABLE"
            or "NO_UPGRADE_AVAILABLE",
        modifierIndex = index,
        modifier = current,
        baseCategory = spec.baseCategory,
        itemLevel = itemLevel,
        currentValue = currentValue,
        maximumAvailableValue = maximum,
        tiers = tiers,
        upgradeTiers = available,
        pobEvaluationRequired = hasUpgrade,
        craftingVerified = false,
        acquisitionVerified = false,
        sourceXmlWritten = false
    }

    print("AFFIX_PRECHECK_JSON:" .. json.encode(result))
end

local ok, err = pcall(run)

if not ok then
    io.stderr:write("AFFIX_PRECHECK_ERROR:" .. tostring(err) .. "\n")
    os.exit(1)
end
