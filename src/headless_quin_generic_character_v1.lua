-- QUIN Generic Character Skeleton V1
-- Runs inside PoB src working directory. Source XML is read only.
-- Usage: luajit headless_quin_generic_character_v1.lua <source.xml> <class> <ascendancy> <level>
package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local function readFile(path)
    local f, err = io.open(path, "rb")
    assert(f, err)
    local s = f:read("*a")
    f:close()
    return s
end

local function run()
    local source = assert(arg[1], "Source XML required")
    local desiredClass = assert(arg[2], "Class name required")
    local desiredAscendancy = assert(arg[3], "Ascendancy name required")
    local level = assert(tonumber(arg[4]), "Numeric level required")
    assert(level == math.floor(level) and level >= 1 and level <= 100, "Invalid level")

    dofile("HeadlessWrapper.lua")
    loadBuildFromXML(readFile(source), "QUIN Generic Skeleton V1")
    assert(main.mode == "BUILD", "Build mode unavailable")

    -- Create a new passive spec; never inherit source allocated nodes.
    local spec = new("PassiveSpec", build, "3_29")
    local classId = nil
    for id, candidate in pairs(spec.tree.classes) do
        if candidate.name == desiredClass then
            assert(classId == nil, "Duplicate class")
            classId = id
        end
    end
    assert(classId ~= nil, "Unknown class: " .. desiredClass)
    spec:ResetNodes()
    spec:SelectClass(classId)

    local ascendId = nil
    for id, candidate in pairs(spec.curClass.classes) do
        if candidate.name == desiredAscendancy then
            assert(ascendId == nil, "Duplicate ascendancy")
            ascendId = id
        end
    end
    assert(ascendId ~= nil, "Unknown ascendancy for class: " .. desiredAscendancy)
    spec:SelectAscendClass(ascendId)
    assert(spec.curClassName == desiredClass)
    assert(spec.curAscendClassName == desiredAscendancy)
    assert(spec.treeVersion == "3_29")

    local count = 0
    for _, node in pairs(spec.allocNodes) do
        count = count + 1
        assert(node.type == "ClassStart" or node.type == "AscendClassStart", "Unexpected inherited node")
    end
    assert(count == 2, "Expected precisely two starting nodes")

    local treeTab = assert(build.treeTab)
    assert(type(treeTab.specList) == "table")
    treeTab.specList[1] = spec
    treeTab:SetActiveSpec(1)
    assert(build.spec == spec)

    build.characterLevel = level
    build.characterLevelAutoMode = false
    build.mainSocketGroup = 1
    wipeGlobalCache()
    build.outputRevision = build.outputRevision + 1
    build.buildFlag = false
    build.skillsTab:UpdateSocketGroups()
    build.calcsTab:BuildOutput()

    local xml = build:SaveDB("QUIN_Generic_Skeleton_v1.xml")
    assert(type(xml) == "string" and #xml > 100, "SaveDB did not return XML")
    assert(xml:find("<PathOfBuilding", 1, true), "Unexpected output")
    -- Python independently checks final class, ascendancy, level, skills and items.
    print("QUIN_BUILD_XML_BEGIN")
    io.write(xml)
    io.write("\n")
    print("QUIN_BUILD_XML_END")
end

local ok, err = pcall(run)
if not ok then
    io.stderr:write("QUIN_GENERIC_SKELETON_ERROR:" .. tostring(err) .. "\n")
    os.exit(1)
end
