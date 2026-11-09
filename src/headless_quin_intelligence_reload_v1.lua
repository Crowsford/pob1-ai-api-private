
package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local xmlPath = assert(arg[1])

local function readFile(path)
    local f = assert(io.open(path, "rb"))
    local content = f:read("*a")
    f:close()
    return content
end

local function run()
    dofile("HeadlessWrapper.lua")
    loadBuildFromXML(readFile(xmlPath), "QUIN INT Reload")

    local spec = assert(build.spec)
    assert(spec.curClassName == "Templar")
    assert(spec.curAscendClassName == "Inquisitor")
    assert(spec.treeVersion == "3_29")
    assert(build.characterLevel == 40)

    local spent, ascend = spec:CountAllocNodes()
    assert(spent == 8, "Expected 8 ordinary points")
    assert(ascend == 0, "Unexpected ascendancy points")

    local group = assert(build.skillsTab.socketGroupList[1])
    assert(group.gemList[1].skillId == "StormBrand")
    assert(tonumber(group.gemList[1].level) == 8)

    build.mainSocketGroup = 1
    wipeGlobalCache()
    build.outputRevision = build.outputRevision + 1
    build.buildFlag = false
    build.skillsTab:UpdateSocketGroups()
    build.calcsTab:BuildOutput()

    local output = assert(build.calcsTab.mainOutput)
    local intelligence = assert(tonumber(output.Int))
    local required = assert(tonumber(output.ReqInt))

    print("Intelligence:", intelligence)
    print("Required Intelligence:", required)
    print("Combined DPS:", tostring(output.CombinedDPS))
    print("Life:", tostring(output.Life))
    print("Points:", spent)

    assert(intelligence >= required)
    assert(intelligence == 93)
    assert(type(output.CombinedDPS) == "number")
    assert(output.CombinedDPS > 0)

    print("INT BASELINE RELOAD: PASS")
end

local ok, err = pcall(run)
if not ok then
    io.stderr:write("QUIN_RELOAD_ERROR:" .. tostring(err) .. "\n")
    os.exit(1)
end
