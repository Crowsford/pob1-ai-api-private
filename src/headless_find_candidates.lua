
-- PoE BuildLab AI — Unique Candidate Discovery v0.1
-- Preliminary text search over native PoB unique definitions.
-- Read-only. Does not verify item mechanics or league availability.

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

local function run()
    local xmlPath = assert(arg[1], "Build XML required")
    local query = assert(arg[2], "Search query required")
    local limit = tonumber(arg[3] or "20")

    assert(query ~= "", "Empty search query")
    assert(
        limit and limit >= 1 and limit <= 100
        and limit == math.floor(limit),
        "Limit must be 1-100"
    )

    dofile("HeadlessWrapper.lua")
    loadBuildFromXML(
        readFile(xmlPath),
        "BuildLab Candidate Discovery"
    )

    assert(data and data.uniques, "PoB unique data unavailable")

    local matches = {}
    local seen = {}
    local totalDefinitions = 0

    for group, definitions in pairs(data.uniques) do
        if type(definitions) == "table" then
            for _, raw in pairs(definitions) do
                if type(raw) == "string" then
                    totalDefinitions = totalDefinitions + 1

                    local name = raw:match("^%s*([^\r\n]+)")

                    if name and not seen[name] then
                        local lower = raw:lower()

                        if lower:find(query:lower(), 1, true) then
                            seen[name] = true

                            table.insert(matches, {
                                name = name,
                                catalogGroup = tostring(group),
                                searchMatch = "RAW_TEXT",
                                mechanicsVerified = false,
                            })
                        end
                    end
                end
            end
        end
    end

    table.sort(matches, function(a, b)
        return a.name < b.name
    end)

    local results = {}

    for i = 1, math.min(#matches, limit) do
        results[#results + 1] = matches[i]
    end

    print("=== UNIQUE CANDIDATE DISCOVERY ===")
    print("Query:", query)
    print("Definitions scanned:", totalDefinitions)
    print("Matching unique names:", #matches)
    print("Returned:", #results)

    for _, item in ipairs(results) do
        print(item.name, "| Group:", item.catalogGroup)
    end

    print("Mechanics verified: NO")
    print("Version verified: NO")
    print("League availability verified: NO")

    print("CANDIDATES_JSON:" .. json.encode({
        schemaVersion = 1,
        status = "PRELIMINARY_MATCHES",
        query = query,
        scannedDefinitions = totalDefinitions,
        matchingNames = #matches,
        items = results,
    }))
end

local ok, err = pcall(run)

if not ok then
    io.stderr:write("CANDIDATE_SEARCH_ERROR:" .. tostring(err) .. "\n")
    os.exit(1)
end
