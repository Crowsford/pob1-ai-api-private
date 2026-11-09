
package.path =
    "../runtime/lua/?.lua;../runtime/lua/?/init.lua;"
    .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local xmlPath = assert(arg[1], "XML argument missing")

local function readFile(path)
    local f = assert(io.open(path, "rb"))
    local data = f:read("*a")
    f:close()
    return data
end

local function calculate()
    wipeGlobalCache()
    build.outputRevision = build.outputRevision + 1
    build.buildFlag = false
    build.skillsTab:UpdateSocketGroups()
    build.calcsTab:BuildOutput()
    return assert(build.calcsTab.mainOutput)
end

local function run()
    dofile("HeadlessWrapper.lua")

    loadBuildFromXML(
        readFile(xmlPath),
        "QUIN Shield Test"
    )

    assert(build.spec.curClassName == "Templar")
    assert(build.spec.curAscendClassName == "Inquisitor")
    assert(build.characterLevel == 40)

    local itemsTab = assert(build.itemsTab)
    local slot = assert(itemsTab.slots["Weapon 2"])
    assert(slot.selItemId == 0, "Offhand is not empty")

    local before = calculate()

    print("=== BEFORE EQUIPMENT ===")
    print("Life:", tostring(before.Life))
    print("Armour:", tostring(before.Armour))
    print("Block:", tostring(before.BlockChance))
    print("Spell Block:", tostring(before.SpellBlockChance))
    print("DPS:", tostring(before.CombinedDPS))

    local raw = table.concat({
        "Rarity: NORMAL",
        "Splintered Tower Shield"
    }, "\n")

    local item = new("Item", raw)

    assert(item.base, "Item base not recognized")
    assert(item.type == "Shield", "Expected Shield")

    local req = item.base.req or {}

    local strength = assert(tonumber(before.Str))
    local dexterity = assert(tonumber(before.Dex))
    local intelligence = assert(tonumber(before.Int))

    assert((req.level or 0) <= build.characterLevel,
        "Level requirement not satisfied")
    assert((req.str or 0) <= strength,
        "Strength requirement not satisfied")
    assert((req.dex or 0) <= dexterity,
        "Dexterity requirement not satisfied")
    assert((req.int or 0) <= intelligence,
        "Intelligence requirement not satisfied")

    print("")
    print("=== ITEM VALIDATION ===")
    print("Base:", tostring(item.baseName))
    print("Type:", tostring(item.type))
    print("Character STR:", strength)
    print("Required STR:", tostring(req.str or 0))
    print("Required Level:", tostring(req.level or 0))
    print("REQUIREMENTS: PASS")

    assert(
        itemsTab:IsItemValidForSlot(item, "Weapon 2"),
        "Shield invalid for Weapon 2"
    )

    itemsTab:AddItem(item, true)
    assert(item.id and itemsTab.items[item.id] == item)

    slot:SetSelItemId(item.id)
    itemsTab:PopulateSlots()

    assert(slot.selItemId == item.id, "Equip failed")

    local after = calculate()

    print("")
    print("=== AFTER EQUIPMENT ===")
    print("Equipped Item ID:", item.id)
    print("Life:", tostring(after.Life))
    print("Armour:", tostring(after.Armour))
    print("Block:", tostring(after.BlockChance))
    print("Spell Block:", tostring(after.SpellBlockChance))
    print("DPS:", tostring(after.CombinedDPS))

    assert(
        tonumber(after.BlockChance or 0) >
        tonumber(before.BlockChance or 0),
        "Equipped shield did not increase block chance"
    )

    print("SHIELD EQUIPMENT: PASS")

    local xml = assert(build:SaveDB("QUIN_Shield_Test_v1.xml"))
    assert(type(xml) == "string" and #xml > 100)

    print("QUIN_XML_BEGIN")
    io.write(xml)
    io.write("\n")
    print("QUIN_XML_END")
end

local ok, err = pcall(run)

if not ok then
    io.stderr:write(
        "QUIN_SHIELD_ERROR:" .. tostring(err) .. "\n"
    )
    os.exit(1)
end
