
-- PoE BuildLab AI - Rare Affix Identification Probe v1
-- Read-only. Uses PoB's native modifier database.

local explicit = dofile("Data/ModExplicit.lua")
local master = dofile("Data/ModMaster.lua")

local checks = {
    { "152% increased Spell Damage", "Prefix", false },
    { "+2 to Level of all Spell Skill Gems", "Prefix", false },
    { "+4 to Level of all Chaos Spell Skill Gems", "Prefix", false },
    { "+43% to Chaos Damage over Time Multiplier", "Suffix", false },
    { "+13% Chance to Block Spell Damage", "Suffix", false },
    { "+13% Chance to Block Attack Damage", "Suffix", true },
}

local function normalize(s)
    return (s:gsub("%(%d+%-%d+%)", "#"):gsub("%d+", "#"))
end


local function matches(mod, actual)
    local lines = {}

    for _, v in ipairs(mod) do
        if type(v) == "string" then
            table.insert(lines, v)
        end
    end

    -- Пока поддерживаем только однострочные аффиксы.
    if #lines ~= 1 then
        return false
    end

    local template = lines[1]

    -- Фиксированный модификатор: точное совпадение.
    -- Например: +2 to Level of all Spell Skill Gems
    if template == actual then
        return true
    end

    -- Модификатор с диапазоном.
    -- Например: (150-174)% increased Spell Damage
    local low, high = template:match("%((%d+)%-(%d+)%)")

    if not (low and high) then
        return false
    end

    local value = actual:match("(%d+)")

    if not value then
        return false
    end

    value = tonumber(value)

    return normalize(template) == normalize(actual)
        and value >= tonumber(low)
        and value <= tonumber(high)
end


local function staffWeight(mod)
    for i, key in ipairs(mod.weightKey or {}) do
        if key == "staff" then
            return mod.weightVal[i] or 0
        end
    end
    return 0
end

local prefixes, suffixes = 0, 0

print("=== RARE AFFIX IDENTIFICATION ===")

for _, check in ipairs(checks) do
    local text, expectedType, crafted = unpack(check)
    local candidates = {}

    if crafted then
        for i, mod in ipairs(master) do
            if mod.type == expectedType
                and mod.types and mod.types.Staff
                and mod.level <= 86
                and matches(mod, text) then
                table.insert(candidates, "Master #" .. i)
            end
        end
    else
        for id, mod in pairs(explicit) do
            if mod.type == expectedType
                and mod.level <= 86
                and staffWeight(mod) > 0
                and matches(mod, text) then
                table.insert(candidates, id)
            end
        end
    end

    table.sort(candidates)

    print("\n" .. text)
    print("Type:", expectedType)
    print("Matches:", #candidates)

    for _, id in ipairs(candidates) do
        print("  " .. id)
    end

    assert(#candidates == 1,
        "Expected exactly one match for: " .. text)

    if expectedType == "Prefix" then
        prefixes = prefixes + 1
    else
        suffixes = suffixes + 1
    end
end

print("\n=== SUMMARY ===")
print("Prefixes:", prefixes)
print("Suffixes:", suffixes)

assert(prefixes == 3 and suffixes == 3,
    "Invalid prefix/suffix distribution")

print("Result: PASS")
print("Note: affix identification only.")
print("Fracture acquisition and crafting legality: NOT VERIFIED")
