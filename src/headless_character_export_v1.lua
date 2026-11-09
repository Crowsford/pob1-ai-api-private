-- PoE BuildLab AI: Character Export v1
-- Creates a new character through native PoB APIs.
-- Outputs XML to stdout; never writes source build files.

package.path =
    "../runtime/lua/?.lua;../runtime/lua/?/init.lua;"
    .. package.path

package.cpath = "../runtime/?.dll;" .. package.cpath

local function readFile(path)
    local f, err = io.open(path, "rb")
    assert(f, err)
    local value = f:read("*a")
    f:close()
    return value
end

local function run()
    local source = assert(arg[1], "Source XML required")

    dofile("HeadlessWrapper.lua")

    loadBuildFromXML(
        readFile(source),
        "QUIN Character Export"
    )

    assert(main.mode == "BUILD")
    assert(build.spec.curClassName == "Scion")

    -- Construct a new independent 3.29 tree.
    local spec = new("PassiveSpec", build, "3_29")

    local classId

    for id, class in pairs(spec.tree.classes) do
        if class.name == "Templar" then
            assert(classId == nil)
            classId = id
        end
    end

    assert(classId, "Templar not found")

    spec:ResetNodes()
    spec:SelectClass(classId)

    local ascendId

    for id, ascend in pairs(spec.curClass.classes) do
        if ascend.name == "Inquisitor" then
            assert(ascendId == nil)
            ascendId = id
        end
    end

    assert(ascendId, "Inquisitor not found")

    spec:SelectAscendClass(ascendId)

    assert(spec.curClassName == "Templar")
    assert(spec.curAscendClassName == "Inquisitor")
    assert(spec.treeVersion == "3_29")

    local count = 0

    for _, node in pairs(spec.allocNodes) do
        count = count + 1

        assert(
            node.type == "ClassStart"
            or node.type == "AscendClassStart",
            "Unexpected passive node"
        )
    end

    assert(count == 2, "Unexpected initial nodes")

    -- Attach the independent tree to this temporary build.
    local treeTab = assert(build.treeTab)

    assert(type(treeTab.specList) == "table")

    treeTab.specList[1] = spec
    treeTab:SetActiveSpec(1)

    assert(build.spec == spec)
    assert(build.spec.curClassName == "Templar")

    -- Create a level 40 research skeleton.
    build.characterLevel = 40
    build.characterLevelAutoMode = false
    build.mainSocketGroup = 1

    wipeGlobalCache()
    build.outputRevision = build.outputRevision + 1
    build.buildFlag = false
    build.skillsTab:UpdateSocketGroups()
    build.calcsTab:BuildOutput()

    -- Native PoB serialization.
    local xml = build:SaveDB("QUIN_Templar_Inquisitor_v1.xml")

    assert(type(xml) == "string")
    assert(#xml > 100)
    assert(xml:find("<PathOfBuilding", 1, true))
    assert(xml:find('className="Templar"', 1, true))
    assert(xml:find('ascendClassName="Inquisitor"', 1, true))
    assert(xml:find('treeVersion="3_29"', 1, true))

    print("QUIN_BUILD_XML_BEGIN")
    io.write(xml)
    io.write("\n")
    print("QUIN_BUILD_XML_END")
end

local ok, err = pcall(run)

if not ok then
    io.stderr:write(
        "CHARACTER_EXPORT_ERROR:"
        .. tostring(err) .. "\n"
    )
    os.exit(1)
end
