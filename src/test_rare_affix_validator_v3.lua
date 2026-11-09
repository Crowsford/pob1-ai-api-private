
-- PoE BuildLab AI - Rare Affix Validator v3 Tests
-- Read-only. No character XML required.

local validator = dofile("rare_affix_validator_v3.lua")

local original = {
    { text = "152% increased Spell Damage" },
    { text = "+43% to Chaos Damage over Time Multiplier" },
    { text = "+2 to Level of all Spell Skill Gems" },
    { text = "+13% Chance to Block Spell Damage" },
    {
        text = "+13% Chance to Block Attack Damage",
        crafted = true
    },
    {
        text = "+4 to Level of all Chaos Spell Skill Gems",
        fractured = true
    }
}

local function copyMods(mods)
    local result = {}
    for i, m in ipairs(mods) do
        result[i] = {
            text = m.text,
            crafted = m.crafted,
            fractured = m.fractured
        }
    end
    return result
end

local function check(name, mods, level, expectedStatus, codes)
    local result = validator.validate({
        baseCategory = "staff",
        itemLevel = level,
        mods = mods
    })

    assert(result.status == expectedStatus,
        name .. ": unexpected status " .. result.status)

    for _, code in ipairs(codes or {}) do
        local found = false
        for _, err in ipairs(result.errors) do
            if err.code == code then
                found = true
                break
            end
        end
        assert(found, name .. ": missing error " .. code)
    end

    print(name .. ": PASS")
    print("  Status:", result.status)
    print("  Prefixes:", result.prefixes)
    print("  Suffixes:", result.suffixes)
    print("  Errors:", #result.errors)

    return result
end

print("=== RARE AFFIX VALIDATOR V3 TESTS ===")

-- 1. Original valid fixture
local positive = check(
    "T01 ORIGINAL",
    copyMods(original),
    86,
    "BASIC_CHECKS_PASSED"
)

assert(positive.prefixes == 3)
assert(positive.suffixes == 3)

for i, mod in ipairs(positive.mods) do
    assert(mod.status == "MATCHED",
        "T01: unresolved mod " .. i)
    assert(#mod.candidates == 1,
        "T01: ambiguous mod " .. i)
end

-- 2. Fourth prefix and group collision
local extraPrefix = copyMods(original)
extraPrefix[#extraPrefix + 1] = {
    text = "+1 to Level of all Spell Skill Gems"
}

check(
    "T02 EXTRA PREFIX",
    extraPrefix,
    86,
    "REJECTED",
    {
        "TOO_MANY_PREFIXES",
        "GROUP_CONFLICT"
    }
)

-- 3. Impossible modifier value
local invalidValue = copyMods(original)
invalidValue[2].text =
    "+76% to Chaos Damage over Time Multiplier"

check(
    "T03 INVALID VALUE",
    invalidValue,
    86,
    "REJECTED",
    { "UNKNOWN_OR_OUT_OF_RANGE" }
)

-- 4. Item level too low
check(
    "T04 LOW ITEM LEVEL",
    copyMods(original),
    1,
    "REJECTED",
    { "ITEM_LEVEL_TOO_LOW" }
)

print("=== FINAL ===")
print("Functional tests: 4/4 PASS")
print("Character XML loaded: NO")
print("Source files modified: NO")
print("Result: PASS")
