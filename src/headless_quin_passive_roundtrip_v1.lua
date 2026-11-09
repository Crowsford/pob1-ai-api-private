-- QUIN Passive Roundtrip V1: independent read-only PoB load and recalculation.
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
    local xmlPath = assert(arg[1], "Path to PoB XML required")
    dofile("HeadlessWrapper.lua")
    loadBuildFromXML(readFile(xmlPath), "QUIN Passive Roundtrip V1")
    assert(main.mode == "BUILD", "Expected BUILD mode")
    local spec = assert(build.spec, "Active passive spec missing")
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
