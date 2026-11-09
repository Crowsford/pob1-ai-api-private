-- PoE BuildLab AI: Character Reload Validation v1
-- Loads an exported character and validates the passive tree.
-- Read-only: no XML writes.

package.path =
    "../runtime/lua/?.lua;../runtime/lua/?/init.lua;"
    .. package.path

package.cpath = "../runtime/?.dll;" .. package.cpath

local function readFile(path)
    local f, err = io.open(path, "rb")
    assert(f, err)
    local data = f:read("*a")
    f:close()
    return data
end

local function run()
    local xmlPath = assert(arg[1], "XML path required")

    dofile("HeadlessWrapper.lua")

    loadBuildFromXML(
        readFile(xmlPath),
        "QUIN Reload Validation"
    )

    assert(main.mode == "BUILD", "Build mode unavailable")

    local spec = assert(build.spec, "Passive tree missing")

    print("=== QUIN CHARACTER RELOAD V1 ===")

    print("Class:", spec.curClassName)
    print("Ascendancy:", spec.curAscendClassName)
    print("Level:", build.characterLevel)
    print("Tree version:", spec.treeVersion)
    print("Class ID:", spec.curClassId)
    print("Ascendancy ID:", spec.curAscendClassId)

    assert(spec.curClassName == "Templar")
    assert(spec.curAscendClassName == "Inquisitor")
    assert(build.characterLevel == 40)
    assert(spec.treeVersion == "3_29")
    assert(spec.curClassId == 5)
    assert(spec.curAscendClassId == 1)

    local expected = {
        [61525] = true,
        [61871] = true
    }

    local count = 0

    print("")
    print("=== ALLOCATED NODES ===")

    for id, node in pairs(spec.allocNodes) do
        count = count + 1

        print(
            "ID:", id,
            "TYPE:", tostring(node.type),
            "NAME:", tostring(node.dn or node.name)
        )

        assert(expected[id], "Unexpected allocated node")
        assert(node.alloc, "Node is not allocated")
    end

    assert(count == 2, "Unexpected node count")

    for id in pairs(expected) do
        assert(spec.allocNodes[id], "Expected node missing")
    end

    local normal, ascendancy = spec:CountAllocNodes()

    print("")
    print("Ordinary points:", normal)
    print("Ascendancy points:", ascendancy)

    assert(normal == 0)
    assert(ascendancy == 0)

    print("")
    print("=== CALCULATION TEST ===")

    wipeGlobalCache()
    build.outputRevision = build.outputRevision + 1
    build.buildFlag = false

    build.skillsTab:UpdateSocketGroups()
    build.calcsTab:BuildOutput()

    local output = assert(
        build.calcsTab.mainOutput,
        "Calculation output missing"
    )

    print("Life:", tostring(output.Life))
    print("Mana:", tostring(output.Mana))
    print("Energy Shield:", tostring(output.EnergyShield))

    assert(
        type(output.Life) == "number",
        "Life calculation unavailable"
    )

    assert(
        type(output.Mana) == "number",
        "Mana calculation unavailable"
    )

    print("")
    print("CLASS VALIDATION: PASS")
    print("TREE VALIDATION: PASS")
    print("POB CALCULATION: PASS")
    print("RELOAD VALIDATION: PASS")
    print("FILES MODIFIED: NO")
end

local ok, err = pcall(run)

if not ok then
    io.stderr:write(
        "CHARACTER_RELOAD_ERROR:"
        .. tostring(err) .. "\n"
    )
    os.exit(1)
end
