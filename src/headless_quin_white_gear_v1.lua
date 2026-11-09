
package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local xmlPath = assert(arg[1])

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
    loadBuildFromXML(readFile(xmlPath), "QUIN White Gear")

    assert(build.spec.curClassName == "Templar")
    assert(build.spec.curAscendClassName == "Inquisitor")
    assert(build.characterLevel == 40)
    assert(build.spec:CountAllocNodes() == 8)

    local tab = assert(build.itemsTab)
    local before = calculate()

    assert(tonumber(before.Int) == 93)

    local shieldSlot = assert(tab.slots["Weapon 2"])
    assert(shieldSlot.selItemId ~= 0)

    local equipment = {
        {"Weapon 1", "Spiraled Wand"},
        {"Body Armour", "Silk Robe"},
        {"Helmet", "Bone Circlet"},
        {"Gloves", "Embroidered Gloves"},
        {"Boots", "Scholar Boots"},
        {"Belt", "Leather Belt"},
        {"Amulet", "Onyx Amulet"},
        {"Ring 1", "Ruby Ring"},
        {"Ring 2", "Sapphire Ring"},
    }

    print("=== QUIN WHITE GEAR EQUIPMENT ===")
    print("Initial Life:", tostring(before.Life))
    print("Initial DPS:", tostring(before.CombinedDPS))

    for _, entry in ipairs(equipment) do
        local slotName = entry[1]
        local baseName = entry[2]
        local slot = assert(tab.slots[slotName])

        assert(slot.selItemId == 0, "Slot occupied: " .. slotName)

        local item = new(
            "Item",
            "Rarity: NORMAL\n" .. baseName
        )

        assert(item.base, "Unrecognized base: " .. baseName)

        local req = item.base.req or {}
        local current = calculate()

        assert((req.level or 0) <= build.characterLevel,
            "Level requirement: " .. baseName)
        assert((req.str or 0) <= tonumber(current.Str),
            "STR requirement: " .. baseName)
        assert((req.dex or 0) <= tonumber(current.Dex),
            "DEX requirement: " .. baseName)
        assert((req.int or 0) <= tonumber(current.Int),
            "INT requirement: " .. baseName)

        assert(tab:IsItemValidForSlot(item, slotName),
            "Invalid slot: " .. slotName)

        tab:AddItem(item, true)
        assert(item.id and tab.items[item.id] == item)

        slot:SetSelItemId(item.id)
        assert(slot.selItemId == item.id)

        print(
            "EQUIPPED:", slotName,
            "|", baseName,
            "| ID:", item.id
        )
    end

    tab:PopulateSlots()

    local after = calculate()

    print("")
    print("=== EQUIPMENT RESULTS ===")

    for _, key in ipairs({
        "Life", "Mana", "Armour", "Evasion",
        "EnergyShield", "BlockChance",
        "SpellBlockChance", "CombinedDPS",
        "Str", "Dex", "Int"
    }) do
        print(
            key .. ":",
            tostring(before[key]),
            "->",
            tostring(after[key])
        )
    end

    assert(tab.slots["Weapon 2"].selItemId ~= 0)
    assert(tonumber(after.BlockChance or 0) >= 24)

    print("EQUIPMENT CALCULATION: PASS")

    local xml = assert(build:SaveDB("QUIN_White_Gear_v1.xml"))
    assert(type(xml) == "string" and #xml > 100)

    print("QUIN_XML_BEGIN")
    io.write(xml)
    io.write("\n")
    print("QUIN_XML_END")
end

local ok, err = pcall(run)

if not ok then
    io.stderr:write(
        "QUIN_GEAR_ERROR:" .. tostring(err) .. "\n"
    )
    os.exit(1)
end
