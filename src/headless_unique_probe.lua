
-- PoE BuildLab AI — Native Unique Probe v1
-- Read-only runtime inspection of PoB Item objects.

package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local json = require("dkjson")

local function run()
    local xmlPath = assert(arg[1], "Build XML path required")

    dofile("HeadlessWrapper.lua")
    loadBuildFromXML(
        assert(io.open(xmlPath, "rb")):read("*a"),
        "BuildLab Unique Probe"
    )

    assert(data and data.uniques, "PoB unique catalog unavailable")
    assert(type(new) == "function", "PoB item constructor unavailable")

    local wanted = {
        ["Anathema"] = true,
        ["Goldrim"] = true,
        ["Tabula Rasa"] = true,
        ["Breath of the Council"] = true,
    }

    local results = {}

    local function simpleLines(lines)
        local output = {}
        if type(lines) ~= "table" then
            return output
        end

        for _, line in ipairs(lines) do
            if type(line) == "string" then
                table.insert(output, line)
            elseif type(line) == "table" then
                table.insert(output, {
                    line = line.line or line.text or json.null,
                    type = line.type or json.null,
                })
            end
        end

        return output
    end

    for itemType, definitions in pairs(data.uniques) do
        if type(definitions) == "table" then
            for _, raw in pairs(definitions) do
                if type(raw) == "string" then
                    local name = raw:match("^%s*([^\r\n]+)")

                    if name and wanted[name] then
                        local ok, item = pcall(
                            new, "Item", raw, "UNIQUE", true
                        )

                        assert(ok, tostring(item))
                        assert(item, "Item constructor returned nil")

                        table.insert(results, {
                            name = name,
                            itemType = itemType,
                            parsedName = item.name or json.null,
                            baseName = item.baseName or json.null,
                            baseFound = item.base ~= nil,
                            selectedVersion = item.selectedVersion or json.null,
                            versionList = simpleLines(item.versionList),
                            variantList = simpleLines(item.variantList),
                            implicitModLines = simpleLines(item.implicitModLines),
                            explicitModLines = simpleLines(item.explicitModLines),
                            hasBuildModList =
                                type(item.BuildModList) == "function",
                            hasNormaliseVariantSelections =
                                type(item.NormaliseVariantSelections) == "function",
                            hasBuildItem =
                                type(item.BuildItem) == "function",
                        })
                    end
                end
            end
        end
    end

    assert(#results == 4, "Expected four unique items; got " .. #results)

    print("UNIQUE_PROBE_JSON:" .. json.encode({
        status = "RUNTIME_INSPECTED",
        count = #results,
        items = results,
    }))
end

local ok, err = xpcall(run, debug.traceback)

if not ok then
    print("UNIQUE_PROBE_ERROR:" .. tostring(err))
    os.exit(1)
end
