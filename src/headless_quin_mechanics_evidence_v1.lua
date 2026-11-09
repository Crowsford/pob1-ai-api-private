-- QUIN Mechanics Evidence Export V1
-- Read-only catalog extraction from the currently installed Path of Building data.
-- Usage: luajit headless_quin_mechanics_evidence_v1.lua <build.xml> <exact active gem name>
package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local function readFile(path)
    local f, err = io.open(path, "rb")
    assert(f, err)
    local data = f:read("*a")
    f:close()
    return data
end

local function safeString(value)
    if type(value) == "string" then return value end
    if type(value) == "number" or type(value) == "boolean" then return tostring(value) end
    return nil
end

local function stringStats(arr)
    local result = {}
    if type(arr) ~= "table" then return result end
    for _, s in ipairs(arr) do
        local value = safeString(s)
        if value then result[#result + 1] = value end
    end
    return result
end

local function safeTags(tags)
    local result = {}
    if type(tags) ~= "table" then return result end
    for k, v in pairs(tags) do
        if type(k) == "string" and (type(v) == "string" or type(v) == "number" or type(v) == "boolean") then
            result[k] = v
        end
    end
    return result
end

local function run()
    local xmlPath = assert(arg[1], "Existing XML required")
    local exactSkill = assert(arg[2], "Exact skill name required")
    local json = require("dkjson")
    dofile("HeadlessWrapper.lua")
    loadBuildFromXML(readFile(xmlPath), "QUIN Mechanics Evidence V1")

    assert(main.mode == "BUILD", "PoB build mode unavailable")
    local spec = assert(build.spec, "Passive tree unavailable")
    local ascendancy = assert(spec.curAscendClassName, "Ascendancy not set")
    assert(ascendancy ~= "None" and ascendancy ~= "nil", "Real ascendancy required")
    assert(spec.treeVersion == "3_29", "Expected tree version 3_29")

    local nodes = {}
    for id, node in pairs(spec.nodes) do
        if node.ascendancyName == ascendancy then
            nodes[#nodes + 1] = {
                id = tonumber(id) or id,
                name = safeString(node.dn or node.name) or "",
                type = safeString(node.type) or "",
                stats = stringStats(node.sd),
                allocated = node.alloc == true,
                ascendancyName = ascendancy
            }
        end
    end
    table.sort(nodes, function(a, b) return tonumber(a.id) < tonumber(b.id) end)
    assert(#nodes > 0, "No ascendancy nodes found; inspect node.ascendancyName in this PoB version")

    -- The game-data catalog is distinct from an equipped/working skill.
    local gems = assert(dofile("Data/Gems.lua"), "Gem catalog unavailable")
    local matches = {}
    for id, gem in pairs(gems) do
        if type(gem) == "table" and gem.name == exactSkill then
            local tags = safeTags(gem.tags)
            matches[#matches + 1] = {
                catalogKey = tostring(id),
                name = exactSkill,
                baseTypeName = safeString(gem.baseTypeName),
                gameId = safeString(gem.gameId),
                variantId = safeString(gem.variantId),
                grantedEffectId = safeString(gem.grantedEffectId),
                tags = tags,
                active = tags.grants_active_skill == true,
                support = tags.support == true
            }
        end
    end
    table.sort(matches, function(a, b) return a.catalogKey < b.catalogKey end)
    assert(#matches > 0, "Exact gem name not found in PoB catalog")
    local hasActive = false
    for _, gem in ipairs(matches) do
        if gem.active and not gem.support then hasActive = true end
    end
    assert(hasActive, "Requested skill is not listed as an active non-support gem")

    local result = {
        schemaVersion = 1,
        source = "Installed Path of Building 3.29 tree and Data/Gems.lua",
        className = spec.curClassName,
        ascendancy = ascendancy,
        level = build.characterLevel,
        treeVersion = spec.treeVersion,
        selectedPrimarySkillName = exactSkill,
        ascendancyNodes = nodes,
        gemVariants = matches,
        scope = {
            ascendancyNodesAreCatalogEntries = true,
            gemVariantsAreCatalogEntries = true,
            skillEquippedOrDpsCalculated = false,
            claimedSkillAscendancySynergyVerified = false,
            realInGameFreezeChanceVerified = false,
            leagueStarterFeasibilityVerified = false,
            sourceXMLModified = false
        }
    }
    local encoded, err = json.encode(result)
    assert(type(encoded) == "string", tostring(err))
    print("QUIN_MECHANICS_EVIDENCE_JSON:" .. encoded)
end

local ok, err = pcall(run)
if not ok then
    io.stderr:write("QUIN_MECHANICS_EVIDENCE_ERROR:" .. tostring(err) .. "\n")
    os.exit(1)
end
