
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
    dofile("HeadlessWrapper.lua")
    loadBuildFromXML(readFile(assert(arg[1])), "QUIN Skill Check")


    print("=== LOADED BUILD DIAGNOSTICS ===")
    print("Class:", tostring(build.spec.curClassName))
    print("Ascendancy:", tostring(build.spec.curAscendClassName))
    print("Level:", tostring(build.characterLevel))
    print("Tree version:", tostring(build.spec.treeVersion))
    print("Class ID:", tostring(build.spec.curClassId))
    print("Ascendancy ID:", tostring(build.spec.curAscendClassId))
    print("Main socket group:", tostring(build.mainSocketGroup))

    local groups = build.skillsTab.socketGroupList
    print("Socket groups:", #groups)

    for i, group in ipairs(groups) do
        print("GROUP:", i)
        print("Enabled:", tostring(group.enabled))
        print("Slot enabled:", tostring(group.slotEnabled))
        print("Slot:", tostring(group.slot))

        for j, gem in ipairs(group.gemList or {}) do
            print(
                "GEM:", j,
                "Skill ID:", tostring(gem.skillId),
                "Name:", tostring(gem.nameSpec or gem.name),
                "Level:", tostring(gem.level)
            )
        end
    end

    assert(build.spec.curClassName == "Templar")
    assert(build.spec.curAscendClassName == "Inquisitor")
    assert(build.characterLevel == 40)
    assert(build.spec.treeVersion == "3_29")

    local group = assert(build.skillsTab.socketGroupList[1])
    local gem = assert(group.gemList[1])

    print("=== STORM BRAND POB CHECK ===")
    print("Skill ID:", tostring(gem.skillId))
    print("Gem Level:", tostring(gem.level))
    print("Group Enabled:", tostring(group.enabled))
    print("Slot Enabled:", tostring(group.slotEnabled))

    assert(gem.skillId == "StormBrand", "Wrong skill ID")

    build.mainSocketGroup = 1
    wipeGlobalCache()
    build.outputRevision = build.outputRevision + 1
    build.buildFlag = false
    build.skillsTab:UpdateSocketGroups()
    build.calcsTab:BuildOutput()

    local output = assert(build.calcsTab.mainOutput)
    local calcGroup = assert(build.skillsTab.socketGroupList[1])

    print("Calculated Group Enabled:", tostring(calcGroup.enabled))
    print("Calculated Slot Enabled:", tostring(calcGroup.slotEnabled))
    print("Combined DPS:", tostring(output.CombinedDPS))
    print("Hit Speed:", tostring(output.HitSpeed))
    print("Cast Rate:", tostring(output.CastRate))
    print("Life:", tostring(output.Life))
    print("Mana:", tostring(output.Mana))
    print("Intelligence:", tostring(output.Int))

    assert(calcGroup.enabled, "Skill group disabled")
    assert(calcGroup.slotEnabled, "Skill slot disabled")
    assert(
        type(output.CombinedDPS) == "number"
            and output.CombinedDPS > 0,
        "Storm Brand damage not calculated"
    )

    print("STORM_BRAND_CALCULATION: PASS")
end

local ok, err = pcall(run)
if not ok then
    io.stderr:write("QUIN_SKILL_ERROR:" .. tostring(err) .. "\n")
    os.exit(1)
end
