-- QUIN Skill Change PoB probe V1; PoB 3.29; read-only and BOM safe.
-- Run from PoB/src: luajit headless_quin_skill_change_probe_v1.lua <XML> <gem display name> <effect id>
package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local function file(path)
    local f, err = io.open(path, "rb")
    assert(f, err)
    local s = f:read("*a")
    f:close()
    if s:sub(1, 3) == "\239\187\191" then s = s:sub(4) end
    return s
end
local function emit(key, value)
    value = tostring(value or "")
    assert(not value:find("[\t\r\n]"), "unsafe QSK output")
    print("QSK\t" .. key .. "\t" .. value)
end

local function run()
    local xml = assert(arg[1], "XML file required")
    local wantedName = assert(arg[2], "Skill display name required")
    local wantedId = assert(arg[3], "GrantedEffectId required")
    -- Keep arg[1] for the same startup behavior as confirmed diagnostic V2.
    dofile("HeadlessWrapper.lua")
    assert(main and type(main) == "table", "PoB global main not initialized")
    loadBuildFromXML(file(xml), "QUIN Skill Change Probe V1")
    assert(main.mode == "BUILD", "PoB rejected XML, mode=" .. tostring(main.mode))
    assert(build and build.spec and build.skillsTab and build.calcsTab, "PoB build not initialized")
    local spec = build.spec
    build.skillsTab:UpdateSocketGroups()
    local groups = assert(build.skillsTab.socketGroupList, "socket group list missing")
    local found, mainId = 0, nil
    local supportNames = {}
    for gi, group in ipairs(groups) do
        for _, gem in ipairs(group.gemList or {}) do
            local d = gem.gemData
            local name = d and d.name or nil
            if d and d.grantedEffect and d.grantedEffect.support then
                supportNames[#supportNames+1] = name or "(unnamed support)"
            end
            if name == wantedName then
                found = found + 1
            end
        end
    end
    assert(found == 1, "Expected one loaded PoB gem named " .. wantedName .. ", found " .. found)
    local mainGroup = groups[build.mainSocketGroup or 1]
    assert(mainGroup, "main socket group missing")
    local entry = mainGroup.displaySkillList and mainGroup.displaySkillList[mainGroup.mainActiveSkill or 1]
    local activeEffect = entry and entry.activeEffect
    local effect = activeEffect and activeEffect.grantedEffect
    mainId = effect and effect.id or nil
    -- Fail closed: a skill's presence is NOT proof it is selected for PoB's main calculation.
    assert(mainId, "PoB selected main effect cannot be determined")
    assert(mainId == wantedId, "PoB selected effect " .. tostring(mainId) .. " rather than " .. wantedId)

    wipeGlobalCache()
    build.outputRevision = build.outputRevision + 1
    build.buildFlag = false
    build.skillsTab:UpdateSocketGroups()
    build.calcsTab:BuildOutput()
    local output = assert(build.calcsTab.mainOutput, "Missing numeric output")
    assert(type(output.Life) == "number" and type(output.Mana) == "number", "Life or Mana missing")

    local ids = {}
    for id, node in pairs(spec.allocNodes or {}) do
        if node.alloc then ids[#ids+1] = tostring(id) end
    end
    table.sort(ids, function(a,b) return tonumber(a) < tonumber(b) end)
    table.sort(supportNames)
    emit("CLASS", spec.curClassName)
    emit("ASCENDANCY", spec.curAscendClassName)
    emit("LEVEL", build.characterLevel)
    emit("SKILL_EXPECTED", wantedName)
    emit("SKILL_FOUND_IN_LOADED_POB", "true")
    emit("MAIN_SELECTED_EFFECT", mainId)
    emit("MAIN_SKILL_CHECK", "PASS")
    emit("TREE_ID_LIST", table.concat(ids, ","))
    emit("SUPPORTS", table.concat(supportNames, "|"))
    for _, k in ipairs({"Life","Mana","Armour","Evasion","EnergyShield","TotalDPS","CombinedDPS","FullDPS","EffectiveHitPool"}) do
        if type(output[k]) == "number" then emit("STAT_"..k, output[k]) end
    end
    emit("CALCULATION", "PASS")
end
local ok, err = pcall(run)
if not ok then
    io.stderr:write("QUIN_SKILL_CHANGE_LUA_ERROR: " .. tostring(err) .. "\n")
    os.exit(1)
end
