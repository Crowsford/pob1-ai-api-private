-- QUIN generic PoB reload: independent verification of an exported empty skeleton.
-- Usage: luajit headless_quin_generic_reload_v1.lua <xml> <class> <ascendancy> <level>
-- Read only: never writes XML.
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
    local xmlPath = assert(arg[1], "XML required")
    local wantedClass = assert(arg[2], "Class required")
    local wantedAscend = assert(arg[3], "Ascendancy required")
    local wantedLevel = assert(tonumber(arg[4]), "Level required")
    dofile("HeadlessWrapper.lua")
    loadBuildFromXML(readFile(xmlPath), "QUIN Generic Reload V1")
    assert(main.mode == "BUILD", "BUILD mode missing")
    local spec = assert(build.spec)
    assert(spec.curClassName == wantedClass, "Class mismatch")
    assert(spec.curAscendClassName == wantedAscend, "Ascendancy mismatch")
    assert(build.characterLevel == wantedLevel, "Level mismatch")
    assert(spec.treeVersion == "3_29", "Tree version mismatch")
    local nodes = {}
    for id, node in pairs(spec.allocNodes) do
        assert(node.alloc, "Unallocated start node")
        assert(node.type == "ClassStart" or node.type == "AscendClassStart", "Unexpected passive allocation")
        nodes[#nodes + 1] = id
    end
    assert(#nodes == 2, "Expected 2 start nodes")
    local normal, ascend = spec:CountAllocNodes()
    assert(normal == 0 and ascend == 0, "Unexpected allocated passive points")
    -- No skill groups or items are permitted in this first skeleton test.
    assert(type(build.skillsTab.socketGroupList) == "table", "Skill groups unavailable")
    assert(#build.skillsTab.socketGroupList == 0, "Unexpected skill groups")
    -- The Python wrapper independently verifies XML has no items or gems.
    wipeGlobalCache()
    build.outputRevision = build.outputRevision + 1
    build.buildFlag = false
    build.skillsTab:UpdateSocketGroups()
    build.calcsTab:BuildOutput()
    local output = assert(build.calcsTab.mainOutput, "Calculation output missing")
    assert(type(output.Life) == "number", "Life missing")
    assert(type(output.Mana) == "number", "Mana missing")
    print("=== QUIN GENERIC RELOAD V1 ===")
    print("CLASS:", spec.curClassName)
    print("ASCENDANCY:", spec.curAscendClassName)
    print("LEVEL:", build.characterLevel)
    print("TREE:", spec.treeVersion)
    print("START NODES:", #nodes)
    print("ORDINARY POINTS:", normal)
    print("ASCENDANCY POINTS:", ascend)
    print("LIFE:", output.Life)
    print("MANA:", output.Mana)
    print("RELOAD VALIDATION: PASS")
    print("POB CALCULATION: PASS")
    print("FILES MODIFIED: NO")
end
local ok, err = pcall(run)
if not ok then
    io.stderr:write("QUIN_GENERIC_RELOAD_ERROR:" .. tostring(err) .. "\n")
    os.exit(1)
end
