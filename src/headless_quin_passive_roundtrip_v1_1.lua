-- QUIN Passive Roundtrip V1.1: independent read-only PoB load and recalculation.
-- Usage from PoB/src: luajit headless_quin_passive_roundtrip_v1.lua <xml>
-- Must execute in a separate LuaJIT process for each XML (avoid stale PoB state).
package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local function readFile(p)
    local f, err = io.open(p, "rb")
    assert(f, err)
    local content = f:read("*a")
    f:close()
    return content
end

local function safe(s)
    s = tostring(s or "")
    assert(not s:find("[\r\n\t]"), "Unexpected line control in field")
    return s
end

local function emit(key, value)
    print("QPR\t" .. safe(key) .. "\t" .. safe(value))
end

local function run()
    -- PoB Main:Init() treats arg[1] as a *build import URL*; if we leave
    -- our local XML filepath there, it may switch modes asynchronously.
    -- Capture the filepath and clear the argument BEFORE starting PoB.
    local xmlPath = assert(arg[1], "Path to PoB XML required")
    arg[1] = nil
    dofile("HeadlessWrapper.lua")
    assert(type(loadBuildFromXML) == "function", "HeadlessWrapper loadBuildFromXML unavailable")
    loadBuildFromXML(readFile(xmlPath), "QUIN Passive Roundtrip V1.1")

    -- A build is considered loaded only if PoB entered BUILD mode and
    -- installed its active spec. Do not mask a failed import with a PASS.
    local appMain = (__mainObject__ and __mainObject__.main) or main
    for _ = 1, 4 do
        if appMain and appMain.mode == "BUILD" and build and build.spec then
            break
        end
        runCallback("OnFrame")
    end
    assert(appMain and appMain.mode == "BUILD",
        "Expected BUILD mode after XML load, got " .. tostring(appMain and appMain.mode) ..
        "; prompt=" .. tostring(__mainObject__ and __mainObject__.promptMsg))
    local spec = assert(build and build.spec, "BUILD mode active, but active passive spec missing")
    assert(spec.treeVersion == "3_29", "Expected PoB 3_29 tree")
    assert(type(spec.allocNodes) == "table", "Active allocations missing")

    local normal, other, all = {}, {}, {}
    for id, node in pairs(spec.allocNodes) do
        assert(node.alloc, "Allocated node marked unallocated")
        local sid = tostring(id)
        all[#all + 1] = sid
        local ntype = tostring(node.type or "")
        if ntype ~= "ClassStart" and ntype ~= "AscendClassStart" then
            if ntype == "Normal" or ntype == "Notable" or ntype == "Keystone" or ntype == "JewelSocket" then
                normal[#normal + 1] = sid
            else
                other[#other + 1] = sid .. ":" .. ntype
            end
        end
    end
    table.sort(all, function(a,b) return tonumber(a) < tonumber(b) end)
    table.sort(normal, function(a,b) return tonumber(a) < tonumber(b) end)
    table.sort(other)

    wipeGlobalCache()
    build.outputRevision = build.outputRevision + 1
    build.buildFlag = false
    build.skillsTab:UpdateSocketGroups()
    build.calcsTab:BuildOutput()
    local output = assert(build.calcsTab.mainOutput, "PoB calculation output missing")
    assert(type(output.Life) == "number", "PoB Life calculation missing")
    assert(type(output.Mana) == "number", "PoB Mana calculation missing")

    emit("CLASS", spec.curClassName)
    emit("ASCENDANCY", spec.curAscendClassName or "")
    emit("LEVEL", build.characterLevel)
    emit("TREE", spec.treeVersion)
    emit("ALLOC_ALL", table.concat(all, ","))
    emit("ALLOC_NORMAL", table.concat(normal, ","))
    emit("ALLOC_OTHER", table.concat(other, ","))
    for _, key in ipairs({"Life", "Mana", "Armour", "Evasion", "EnergyShield", "TotalDPS", "CombinedDPS", "FullDPS", "EffectiveHitPool"}) do
        if type(output[key]) == "number" then
            emit("STAT_" .. key, output[key])
        end
    end
    emit("CALCULATION", "PASS")
end

local ok, err = pcall(run)
if not ok then
    io.stderr:write("QUIN_PASSIVE_ROUNDTRIP_LUA_ERROR: " .. tostring(err) .. "\n")
    os.exit(1)
end
