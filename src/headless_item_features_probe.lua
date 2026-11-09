
-- PoE BuildLab AI — Item Features Probe v1
-- Inspects native PoB Item fields.
-- Read-only; no build changes.

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

local wanted = {
    ["Tabula Rasa"] = true,
    ["Goldrim"] = true,
    ["Anathema"] = true,
}

local function summarize(value)
    local kind = type(value)

    if kind == "string"
        or kind == "number"
        or kind == "boolean" then
        return value
    end

    if kind ~= "table" then
        return "<" .. kind .. ">"
    end

    local result = {}
    local count = 0

    for key, entry in pairs(value) do
        count = count + 1

        if count > 30 then
            result["_truncated"] = true
            break
        end

        local entryType = type(entry)

        if entryType == "string"
            or entryType == "number"
            or entryType == "boolean" then
            result[tostring(key)] = entry
        elseif entryType == "table" then
            result[tostring(key)] = "<table>"
        else
            result[tostring(key)] = "<" .. entryType .. ">"
        end
    end

    return result
end

local function interestingField(key)
    local name = tostring(key):lower()

    return name:find("socket", 1, true)
        or name:find("link", 1, true)
        or name:find("require", 1, true)
        or name:find("level", 1, true)
        or name:find("base", 1, true)
end

local function inspect(item, rawName, raw)
    local fields = {}

    for key, value in pairs(item) do
        if interestingField(key) then
            fields[tostring(key)] = summarize(value)
        end
    end

    local relevantRawLines = {}

    for line in raw:gmatch("[^\r\n]+") do
        local lower = line:lower()

        if lower:find("socket", 1, true)
            or lower:find("require", 1, true)
            or lower:find("level", 1, true) then
            table.insert(relevantRawLines, line)
        end
    end

    return {
        name = rawName,
        baseName = item.baseName,
        fields = fields,
        relevantRawLines = relevantRawLines,
    }
end

local function run()
    local xml = assert(arg[1], "Build XML required")

    dofile("HeadlessWrapper.lua")
    loadBuildFromXML(
        readFile(xml),
        "BuildLab Item Features Probe"
    )

    assert(data and data.uniques, "Unique catalog unavailable")

    local results = {}

    for _, definitions in pairs(data.uniques) do
        if type(definitions) == "table" then
            for _, raw in pairs(definitions) do
                if type(raw) == "string" then
                    local name = raw:match("^%s*([^\r\n]+)")

                    if name and wanted[name] then
                        assert(
                            not results[name],
                            "Duplicate item: " .. name
                        )

                        local item = new(
                            "Item", raw, "UNIQUE", true
                        )

                        assert(item and item.base,
                            "Item not recognized: " .. name)

                        results[name] = inspect(item, name, raw)
                    end
                end
            end
        end
    end

    for _, name in ipairs({
        "Tabula Rasa",
        "Goldrim",
        "Anathema"
    }) do
        local result = assert(
            results[name],
            "Missing item: " .. name
        )

        print("\n=== " .. name .. " ===")
        print(json.encode(result, { indent = true }))
    end

    print("\nItems inspected: 3")
    print("Item objects created: YES")
    print("PoB source modified: NO")
    print("Economy database modified: NO")
    print("Result: COMPLETE")
end

local ok, err = xpcall(run, debug.traceback)

if not ok then
    print("ITEM_FEATURES_ERROR:" .. tostring(err))
    os.exit(1)
end
