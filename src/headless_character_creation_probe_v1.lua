-- PoE BuildLab AI
-- Character creation probe v1
-- Independent passive tree in memory only.
-- Does not modify source XML or save any build.

package.path =
    "../runtime/lua/?.lua;../runtime/lua/?/init.lua;"
    .. package.path

package.cpath = "../runtime/?.dll;" .. package.cpath

local function readFile(path)
    local f, err = io.open(path, "rb")
    assert(f, err)

    local content = f:read("*a")
    f:close()

    return content
end

local function run()
    local xmlPath = assert(arg[1], "Source XML required")

    dofile("HeadlessWrapper.lua")

    loadBuildFromXML(
        readFile(xmlPath),
        "Character Creation Probe"
    )

    assert(main.mode == "BUILD")

    print("=== SOURCE CHARACTER ===")
    print("Class:", build.spec.curClassName)
    print("Tree version:", build.spec.treeVersion)

    -- Create a completely independent passive tree.
    local spec = new("PassiveSpec", build, "3_29")

    assert(spec.treeVersion == "3_29")

    local classId = nil

    for id, class in pairs(spec.tree.classes) do
        if class.name == "Templar" then
            assert(classId == nil, "Duplicate Templar class")
            classId = id
        end
    end

    assert(classId ~= nil, "Templar not found")

    spec:ResetNodes()
    spec:SelectClass(classId)

    local ascendancyId = nil

    for id, ascendancy in pairs(spec.curClass.classes) do
        if ascendancy.name == "Inquisitor" then
            assert(
                ascendancyId == nil,
                "Duplicate Inquisitor ascendancy"
            )

            ascendancyId = id
        end
    end

    assert(ascendancyId ~= nil, "Inquisitor not found")

    spec:SelectAscendClass(ascendancyId)

    assert(spec.curClassName == "Templar")
    assert(spec.curAscendClassName == "Inquisitor")
    assert(spec.treeVersion == "3_29")

    print("")
    print("=== NEW CHARACTER TREE ===")

    print("Tree version:", spec.treeVersion)
    print("Class:", spec.curClassName)
    print("Class ID:", spec.curClassId)
    print("Ascendancy:", spec.curAscendClassName)
    print("Ascendancy ID:", spec.curAscendClassId)

    local startId = spec.curClass.startNodeId
    local startNode = assert(spec.nodes[startId])

    assert(startNode.alloc)
    assert(spec.allocNodes[startId] == startNode)

    print("Class start node:", startId)

    local allocated = {}

    for id, node in pairs(spec.allocNodes) do
        allocated[#allocated + 1] = {
            id = id,
            type = node.type,
            ascendancyName = node.ascendancyName
        }
    end

    table.sort(allocated, function(a, b)
        return a.id < b.id
    end)

    print("")
    print("=== ALLOCATED NODES ===")

    for _, node in ipairs(allocated) do
        print(
            node.id,
            node.type,
            tostring(node.ascendancyName)
        )

        assert(
            node.type == "ClassStart"
                or node.type == "AscendClassStart",
            "Unexpected inherited passive node"
        )
    end

    print("Allocated nodes:", #allocated)

    -- Check the original Scion tree is still intact.
    assert(build.spec ~= spec)
    assert(build.spec.curClassName == "Scion")

    print("")
    print("NEW TREE: PASS")
    print("ORIGINAL SPEC UNCHANGED: YES")
    print("XML WRITTEN: NO")
    print("CHARACTER EXPORTED: NO")
end

local ok, err = pcall(run)

if not ok then
    io.stderr:write(
        "CHARACTER_CREATION_ERROR:"
        .. tostring(err) .. "\n"
    )
    os.exit(1)
end
