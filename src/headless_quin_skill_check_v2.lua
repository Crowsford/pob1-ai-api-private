
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
    -- Capture CLI arguments before loading the PoB environment.
    local xmlPath = assert(arg[1], "Missing XML argument")

    dofile("HeadlessWrapper.lua")

    print("XML argument captured: YES")

    loadBuildFromXML(
        readFile(xmlPath),
        "QUIN Skill Check"
    )

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
