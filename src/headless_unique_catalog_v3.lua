
-- PoE BuildLab AI — Universal Unique Provider v1
-- Uses the native PoB Item parser.
-- Challenge-league policy: Current or single version.
-- Read-only. No changes to existing evaluators.

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

local function parseNames(text)
    assert(text and text ~= "", "Item names required")

    local wanted = {}
    local count = 0

    for part in (text .. ","):gmatch("(.-),") do
        local name = part:match("^%s*(.-)%s*$")
        assert(name ~= "", "Empty item name")
        assert(not wanted[name], "Duplicate item name: " .. name)

        wanted[name] = true
        count = count + 1
    end

    assert(count >= 1 and count <= 20, "Request 1-20 items")
    return wanted, count
end

local function filteredMods(modLines, index)
    local output = {}

    for _, mod in ipairs(modLines or {}) do
        assert(
            type(mod) == "table" and type(mod.line) == "string",
            "Unexpected PoB modifier structure"
        )

        local variants = mod.variantList

        if variants == nil or variants[index] == true then
            table.insert(output, mod.line)
        end
    end

    return output
end

local function exportItem(item, raw)
    -- Fail closed on version mechanisms not yet implemented.
    assert(
        not item.versionList or #item.versionList == 0,
        "VersionList needs a separate exporter"
    )
    assert(
        not item.usesVariantGroups,
        "Variant groups are not supported yet"
    )

    local variants = item.variantList
    local selectedIndex = 1
    local selectedName = "Single"

    if variants and #variants > 0 then
        local found = false

        for index, name in ipairs(variants) do
            if name == "Current" then
                assert(not found, "Duplicate Current variant")
                selectedIndex = index
                selectedName = name
                found = true
            end
        end

        assert(
            found,
            "No Current variant: " .. tostring(item.name)
        )
    end

    local availableVariants = {}

    if variants and #variants > 0 then
        for _, name in ipairs(variants) do
            table.insert(availableVariants, name)
        end
    else
        table.insert(availableVariants, "Single")
    end

    -- Export observed item features, without inferring
    -- unsupported mechanics from missing properties.
    local canonicalName = raw:match("^%s*([^\r\n]+)")
    assert(canonicalName, "Missing canonical item name")

    local requirementSource = item.requirements or {}
    local requirements = {}

    for _, key in ipairs({ "level", "str", "dex", "int" }) do
        local value = requirementSource[key]
        requirements[key] = type(value) == "number"
            and value or json.null
    end

    local socketSpec = nil

    for line in raw:gmatch("[^\r\n]+") do
        local value = line:match("^Sockets:%s*(.+)$")
        if value then
            socketSpec = value
            break
        end
    end

    local features = {
        requirements = requirements,
        sockets = {
            parsedCount = type(item.sockets) == "table"
                and #item.sockets or json.null,
            rawSpecification = socketSpec or json.null,
            baseSocketLimit = item.base
                and item.base.socketLimit or json.null,
            linkGroupsVerified = false,
        },
        specialMechanicsVerified = false,
    }

    -- Export all variants for market matching.
    -- Current remains the default for challenge-league builds.
    local variantDetails = {}

    if variants and #variants > 0 then
        for index, variantName in ipairs(variants) do
            table.insert(variantDetails, {
                index = index,
                name = variantName,
                implicitMods = filteredMods(
                    item.implicitModLines, index
                ),
                explicitMods = filteredMods(
                    item.explicitModLines, index
                ),
            })
        end
    else
        table.insert(variantDetails, {
            index = 1,
            name = "Single",
            implicitMods = filteredMods(
                item.implicitModLines, 1
            ),
            explicitMods = filteredMods(
                item.explicitModLines, 1
            ),
        })
    end

    return {
        canonicalName = canonicalName,
        features = features,
        name = item.name,
        baseType = item.baseName,
        selectedVariant = selectedName,
        selectedVariantIndex = selectedIndex,
        availableVariants = availableVariants,
        variantDetails = variantDetails,
        implicitMods = filteredMods(
            item.implicitModLines, selectedIndex
        ),
        explicitMods = filteredMods(
            item.explicitModLines, selectedIndex
        ),
        rawDefinition = raw,
        versionPolicy = "CHALLENGE_LEAGUE_CURRENT",
        status = "POB_MODIFIER_LINES_EXTRACTED",
        fullItemMechanicsVerified = false,
        leagueAvailabilityVerified = false,
    }
end

local function run()
    local xmlPath = assert(arg[1], "Build XML required")
    local wanted, expected = parseNames(arg[2])

    dofile("HeadlessWrapper.lua")
    loadBuildFromXML(
        readFile(xmlPath),
        "BuildLab Unique Catalog"
    )

    assert(data and data.uniques, "PoB uniques unavailable")

    local results = {}
    local found = {}

    for _, definitions in pairs(data.uniques) do
        if type(definitions) == "table" then
            for _, raw in pairs(definitions) do
                if type(raw) == "string" then
                    local name = raw:match("^%s*([^\r\n]+)")

                    if name and wanted[name] then
                        assert(
                            not found[name],
                            "Multiple PoB definitions: " .. name
                        )

                        local item = new(
                            "Item", raw, "UNIQUE", true
                        )

                        assert(
                            item and item.base,
                            "Unrecognized PoB item: " .. name
                        )

                        found[name] = true
                        table.insert(
                            results, exportItem(item, raw)
                        )
                    end
                end
            end
        end
    end

    assert(
        #results == expected,
        "Expected " .. expected ..
        " items, found " .. #results
    )

    table.sort(results, function(a, b)
        return a.name < b.name
    end)

    print("=== POB UNIQUE CATALOG v1 ===")

    for _, item in ipairs(results) do
        print(
            item.name ..
            " | Base: " .. tostring(item.baseType) ..
            " | Variant: " .. item.selectedVariant ..
            " | Implicits: " .. #item.implicitMods ..
            " | Explicits: " .. #item.explicitMods
        )
    end

    print("Items exported: " .. #results)
    print("Version policy: CHALLENGE_LEAGUE_CURRENT")
    print("Full mechanics verified: NO")
    print("League availability verified: NO")
    print("PoB source modified: NO")
    print("Result: PASS")

    print("UNIQUE_CATALOG_JSON:" .. json.encode({
        schemaVersion = 1,
        source = "PoB Item parser",
        status = "PARTIAL_ITEM_DATA",
        itemCount = #results,
        items = results,
    }))
end

local ok, err = xpcall(run, debug.traceback)

if not ok then
    print("UNIQUE_CATALOG_ERROR:" .. tostring(err))
    os.exit(1)
end
