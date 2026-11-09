
-- PoE BuildLab AI — Native Unique Export v1
-- Uses PoB Item parser and variant metadata.
-- Does not modify character, items or PoB source data.

package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local json = require("dkjson")

local function readFile(path)
    local file, err = io.open(path, "rb")
    assert(file, err)
    local content = file:read("*a")
    file:close()
    return content
end

local function linesForVariant(modLines, variantIndex)
    local result = {}

    for _, mod in ipairs(modLines or {}) do
        assert(type(mod) == "table", "Invalid PoB mod object")
        assert(type(mod.line) == "string", "Missing PoB mod line")

        local variants = mod.variantList

        -- An untagged modifier applies to every variant.
        local included = variants == nil

        if variants ~= nil then
            assert(
                type(variants) == "table",
                "Unexpected PoB variant metadata"
            )
            included = variants[variantIndex] == true
        end

        if included then
            table.insert(result, mod.line)
        end
    end

    return result
end

local function contains(lines, expected)
    for _, line in ipairs(lines) do
        if line == expected then
            return true
        end
    end
    return false
end

local function findUnique(name)
    for _, definitions in pairs(data.uniques) do
        if type(definitions) == "table" then
            for _, raw in pairs(definitions) do
                if type(raw) == "string" then
                    local rawName = raw:match("^%s*([^\r\n]+)")

                    if rawName == name then
                        local item = new(
                            "Item", raw, "UNIQUE", true
                        )
                        assert(item and item.base, "Unrecognized item")
                        return item
                    end
                end
            end
        end
    end

    error("Unique not found in PoB: " .. name)
end

local function run()
    local xmlPath = assert(arg[1], "XML path required")

    dofile("HeadlessWrapper.lua")
    loadBuildFromXML(
        readFile(xmlPath),
        "BuildLab Unique Export"
    )

    assert(data and data.uniques, "PoB uniques unavailable")

    local item = findUnique("Breath of the Council")

    assert(
        type(item.variantList) == "table"
        and #item.variantList == 3,
        "Expected three item variants"
    )

    local exported = {}

    for index, name in ipairs(item.variantList) do
        local implicit = linesForVariant(
            item.implicitModLines, index
        )
        local explicit = linesForVariant(
            item.explicitModLines, index
        )

        table.insert(exported, {
            index = index,
            name = name,
            implicitMods = implicit,
            explicitMods = explicit,
        })
    end

    -- Verify that variants do not mix their modifiers.
    local expectedChaos = {
        "(60-80)% increased Chaos Damage",
        "(80-100)% increased Chaos Damage",
        "(80-120)% increased Chaos Damage",
    }

    local expectedArea = {
        "10% increased Area of Effect",
        "10% increased Area of Effect",
        "(10-20)% increased Area of Effect",
    }

    local expectedDuration = {
        "Chaos Skills have 40% increased Skill Effect Duration",
        "Chaos Skills have 40% increased Skill Effect Duration",
        "Chaos Skills have (40-80)% increased Skill Effect Duration",
    }

    for index, variant in ipairs(exported) do
        local mods = variant.explicitMods

        assert(
            contains(mods, expectedChaos[index]),
            "Wrong Chaos Damage in variant " .. index
        )

        assert(
            contains(mods, expectedArea[index]),
            "Wrong Area of Effect in variant " .. index
        )

        assert(
            contains(mods, expectedDuration[index]),
            "Wrong Skill Duration in variant " .. index
        )

        assert(
            contains(
                mods,
                "(260-310)% increased Physical Damage"
            ),
            "Missing shared Physical Damage modifier"
        )

        for other = 1, #expectedChaos do
            if other ~= index then
                assert(
                    not contains(mods, expectedChaos[other]),
                    "Chaos Damage variants mixed"
                )
            end
        end
    end

    -- Select Current for challenge-league builds.
    -- Preserve every variant for historical analysis.
    local currentVariant = nil

    for _, variant in ipairs(exported) do
        if variant.name == "Current" then
            assert(currentVariant == nil, "Duplicate Current variant")
            currentVariant = variant
        end
    end

    assert(currentVariant, "Current variant not found")

    local result = {
        status = "POB_PARSED_VARIANTS_VERIFIED",
        defaultVariant = currentVariant,
        defaultPolicy = "CHALLENGE_LEAGUE_CURRENT",
        name = "Breath of the Council",
        baseType = item.baseName,
        source = "PoB Item parser",
        extractionMethod = "mod.variantList filtering",
        variantCount = #exported,
        variants = exported,
        pobCalculations = 0,
    }

    print("=== POB NATIVE UNIQUE EXPORT v1 ===")

    for _, variant in ipairs(exported) do
        print("")
        print("Variant " .. variant.index .. ": " .. variant.name)

        for _, line in ipairs(variant.implicitMods) do
            print("  IMPLICIT: " .. line)
        end

        for _, line in ipairs(variant.explicitMods) do
            print("  EXPLICIT: " .. line)
        end
    end

    print("")
    print("Variants exported: " .. #exported)
    print("Cross-variant checks: PASS")
    print("PoB source modified: NO")
    print("Economy database modified: NO")
    print("UNIQUE_EXPORT_JSON:" .. json.encode(result))
end

local ok, err = xpcall(run, debug.traceback)

if not ok then
    print("UNIQUE_EXPORT_ERROR:" .. tostring(err))
    os.exit(1)
end
