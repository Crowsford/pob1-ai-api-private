-- QUIN Weapon State Diagnostic V1; read-only PoB 3.29 loader.
-- Usage (from PoB/src): luajit headless_quin_weapon_state_diagnostic_v1.lua <XML> <effectId>
package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local function read_xml(path)
    local f, err = io.open(path, "rb")
    assert(f, err)
    local s = f:read("*a")
    f:close()
    if s:sub(1,3) == "\239\187\191" then s = s:sub(4) end
    return s
end
local function value(v)
    if v == nil then return "<nil>" end
    return tostring(v)
end
local function emit(k, v)
    local s = value(v)
    assert(not s:find("[\t\r\n]"), "unsafe diagnostic output: "..tostring(k))
    print("QWEAPON\t"..k.."\t"..s)
end
local function run()
    local xml = assert(arg[1],"XML path required")
    local wanted = assert(arg[2],"Expected grantedEffectId required")
    dofile("HeadlessWrapper.lua")
    assert(type(main)=="table", "PoB main global missing")
    loadBuildFromXML(read_xml(xml),"QUIN weapon-state diagnostic")
    assert(main.mode == "BUILD", "PoB XML load failed; mode="..value(main.mode))
    assert(build and build.itemsTab and build.skillsTab and build.calcsTab, "PoB build tabs missing")
    build.skillsTab:UpdateSocketGroups()
    local groups = assert(build.skillsTab.socketGroupList, "Socket groups missing")
    local mg = assert(groups[build.mainSocketGroup or 1],"Main skill group missing")
    local entry = mg.displaySkillList and mg.displaySkillList[mg.mainActiveSkill or 1]
    local eff = entry and entry.activeEffect and entry.activeEffect.grantedEffect
    local got = eff and eff.id
    assert(got == wanted, "MAIN_SKILL_MISMATCH: "..value(got).." vs "..wanted)
    wipeGlobalCache()
    build.outputRevision=build.outputRevision+1
    build.buildFlag=false
    build.skillsTab:UpdateSocketGroups()
    build.calcsTab:BuildOutput()
    local output = assert(build.calcsTab.mainOutput, "PoB mainOutput missing")
    local tab = build.itemsTab
    local slot = tab.slots and tab.slots["Weapon 1"]
    local slotid = slot and slot.selItemId
    local selectedItem = slotid and tab.items and tab.items[slotid]
    local activeSet = tab.activeItemSet
    local setWeapon = activeSet and activeSet["Weapon 1"]
    local env = build.calcsTab.mainEnv
    local player = env and env.player
    local playerWeapon = player and player.itemList and player.itemList["Weapon 1"]
    local weaponData = player and player.weaponData1
    local groupSkill = player and player.mainSkill
    emit("MAIN_EFFECT",got)
    emit("CHARACTER_LEVEL",build.characterLevel)
    emit("WEAPON_SET_SECOND",activeSet and activeSet.useSecondWeaponSet)
    emit("WEAPON_SLOT_PRESENT",slot ~= nil)
    emit("WEAPON_SLOT_SEL_ID",slotid)
    emit("ITEMS_TAB_SELECTED_ITEM",selectedItem ~= nil)
    emit("ITEMSET_WEAPON_ITEM_ID",setWeapon and setWeapon.selItemId)
    emit("ENGINE_WEAPON_PRESENT",playerWeapon ~= nil)
    emit("ENGINE_WEAPON_NAME",playerWeapon and playerWeapon.name)
    emit("ENGINE_WEAPON_BASE",playerWeapon and playerWeapon.baseName)
    emit("ENGINE_WEAPON_TYPE",playerWeapon and playerWeapon.base and playerWeapon.base.type)
    emit("ENGINE_WEAPON_REQUIREMENTS",playerWeapon and playerWeapon.requirements and "PRESENT" or "NOT_EXPOSED")
    emit("WEAPON_DATA_TYPE",weaponData and weaponData.type)
    emit("WEAPON_DATA_NAME",weaponData and weaponData.name)
    emit("WEAPON_DATA_ATTACK_RATE",weaponData and weaponData.AttackRate)
    emit("WEAPON_DATA_PHYSICAL_MIN",weaponData and weaponData.PhysicalMin)
    emit("WEAPON_DATA_PHYSICAL_MAX",weaponData and weaponData.PhysicalMax)
    emit("MAIN_SKILL_ATTACK",groupSkill and groupSkill.skillFlags and groupSkill.skillFlags.attack)
    emit("MAIN_SKILL_SPELL",groupSkill and groupSkill.skillFlags and groupSkill.skillFlags.spell)
    for _,key in ipairs({"Life","Mana","TotalDPS","HitDPS","AverageDamage","AttackRate","Speed","HitChance","CritChance","CombinedDPS","FullDPS"}) do
        emit("OUT_"..key,output[key])
    end
    emit("CALCULATION","PASS")
end
local ok,err=pcall(run)
if not ok then io.stderr:write("QUIN_WEAPON_DIAG_ERROR: "..tostring(err).."\n"); os.exit(1) end
