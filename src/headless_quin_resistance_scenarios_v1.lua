
package.path =
    "../runtime/lua/?.lua;../runtime/lua/?/init.lua;"
    .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local xmlPath = assert(arg[1])
local index = assert(tonumber(arg[2]), "Penalty index required")
assert(index == 1 or index == 2 or index == 3)

local penalties = {0, -30, -60}
local expected = penalties[index]

local function readFile(path)
    local f = assert(io.open(path, "rb"))
    local content = f:read("*a")
    f:close()
    return content
end

local function run()
    dofile("HeadlessWrapper.lua")

    loadBuildFromXML(
        readFile(xmlPath),
        "QUIN Resistance Scenario"
    )

    assert(build.spec.curClassName == "Templar")
    assert(build.spec.curAscendClassName == "Inquisitor")
    assert(build.characterLevel == 40)
    assert(build.spec:CountAllocNodes() == 8)

    local config = assert(build.configTab)
    local control = assert(
        config.varControls["resistancePenalty"],
        "Resistance penalty control unavailable"
    )

    -- Select the same option as the PoB Configuration UI.
    control:SetSel(index)

    wipeGlobalCache()
    build.outputRevision = build.outputRevision + 1
    build.buildFlag = false
    build.skillsTab:UpdateSocketGroups()
    build.calcsTab:BuildOutput()

    local output = assert(build.calcsTab.mainOutput)

    local fire = assert(tonumber(output.FireResist))
    local cold = assert(tonumber(output.ColdResist))
    local lightning = assert(tonumber(output.LightningResist))
    local chaos = assert(tonumber(output.ChaosResist))

    print("=== RESISTANCE SCENARIO ===")
    print("INDEX:", index)
    print("EXPECTED PENALTY:", expected)
    print("FIRE:", fire)
    print("COLD:", cold)
    print("LIGHTNING:", lightning)
    print("CHAOS:", chaos)
    print("LIFE:", tostring(output.Life))
    print("ENERGY SHIELD:", tostring(output.EnergyShield))
    print("BLOCK:", tostring(output.BlockChance))
    print("DPS:", tostring(output.CombinedDPS))
    print("EHP:", tostring(output.TotalEHP))

    assert(fire == 20 + expected,
        "Fire resistance did not match selected penalty")
    assert(cold == 20 + expected,
        "Cold resistance did not match selected penalty")
    assert(lightning == expected,
        "Lightning resistance did not match selected penalty")
    assert(chaos == expected,
        "Chaos resistance did not match selected penalty")

    assert(tonumber(output.Life) == 559)
    assert(tonumber(output.BlockChance) == 24)

    print("SCENARIO VERIFIED: PASS")
end

local ok, err = pcall(run)

if not ok then
    io.stderr:write(
        "QUIN_RESISTANCE_ERROR:" .. tostring(err) .. "\n"
    )
    os.exit(1)
end
