
package.path =
    "../runtime/lua/?.lua;../runtime/lua/?/init.lua;"
    .. package.path

package.cpath = "../runtime/?.dll;" .. package.cpath

local xmlPath = assert(arg[1])

local function readFile(path)
    local f = assert(io.open(path, "rb"))
    local content = f:read("*a")
    f:close()
    return content
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
    loadBuildFromXML(readFile(xmlPath), "QUIN Implicit Gear")

    assert(build.spec.curClassName == "Templar")
    assert(build.spec.curAscendClassName == "Inquisitor")
    assert(build.characterLevel == 40)
    assert(build.spec:CountAllocNodes() == 8)

    local tab = assert(build.itemsTab)
    local before = calculate()

    assert(tonumber(before.Life) == 529)
    assert(tonumber(before.Int) == 93)

    local targets = {
        {"Weapon 1", "Spiraled Wand", "Adds 1 to 9 Lightning Damage to Spells and Attacks"},
        {"Belt", "Leather Belt", "+25 to maximum Life"},
        {"Amulet", "Onyx Amulet", "+10 to all Attributes"},
        {"Ring 1", "Ruby Ring", "+20% to Fire Resistance"},
        {"Ring 2", "Sapphire Ring", "+20% to Cold Resistance"},
    }

    print("")
    print("=== APPLYING DATABASE IMPLICITS ===")

    for _, entry in ipairs(targets) do
        local slotName = entry[1]
        local baseName = entry[2]
        local implicit = entry[3]

        local slot = assert(tab.slots[slotName])
        local id = assert(slot.selItemId)
        assert(id ~= 0)

        local oldItem = assert(tab.items[id])
        assert(oldItem.baseName == baseName)

        local raw = oldItem:BuildRaw()
        local changed, count = raw:gsub(
            "Implicits: 0",
            "Implicits: 1\n" .. implicit,
            1
        )

        assert(count == 1,
            "Unexpected implicit count: " .. baseName)

        local newItem = new("Item", changed)

        assert(newItem.base, "Unknown base: " .. baseName)
        assert(newItem.baseName == baseName)
        assert(newItem:GetPrimarySlot() == oldItem:GetPrimarySlot())

        local req = newItem.base.req or {}
        local current = calculate()

        assert((req.level or 0) <= build.characterLevel)
        assert((req.str or 0) <= tonumber(current.Str))
        assert((req.dex or 0) <= tonumber(current.Dex))
        assert((req.int or 0) <= tonumber(current.Int))

        assert(tab:IsItemValidForSlot(newItem, slotName))

        newItem.id = id
        tab:AddItem(newItem, true)

        assert(tab.items[id] == newItem)
        assert(slot.selItemId == id)

        local savedRaw = newItem:BuildRaw()

        if baseName == "Ruby Ring" then
            print("")
            print("=== RUBY RING DIAGNOSTICS ===")
            print("EXPECTED IMPLICIT:", implicit)
            print("")
            print("=== RAW PASSED TO ITEM CONSTRUCTOR ===")
            print(changed)
            print("")
            print("=== RAW RETURNED BY POB ===")
            print(savedRaw)
            print("")
            print("=== PARSED ITEM DETAILS ===")
            print("Base:", tostring(newItem.baseName))
            print("Rarity:", tostring(newItem.rarity))
            print("Implicit count:", tostring(newItem.implicitModLines and #newItem.implicitModLines))
            print("Exact text preserved:", tostring(savedRaw:find(implicit, 1, true) ~= nil))
            print("")
            print("DIAGNOSTIC COMPLETE - NO XML EXPORT")
            return
        end

        assert(savedRaw:find(implicit, 1, true),
            "Implicit missing after parsing: " .. baseName)

        print("UPDATED:", slotName, "|", baseName)
        print("IMPLICIT:", implicit)
    end

    tab:PopulateSlots()

    local after = calculate()

    print("")
    print("=== CHARACTER COMPARISON ===")

    for _, key in ipairs({
        "Life", "Mana", "Str", "Dex", "Int",
        "FireResist", "ColdResist", "LightningResist",
        "EnergyShield", "BlockChance",
        "SpellBlockChance", "CombinedDPS"
    }) do
        print(
            key .. ":",
            tostring(before[key]),
            "->",
            tostring(after[key])
        )
    end

    assert(tonumber(after.Life) >= 554)
    assert(tonumber(after.Int) >= 103)
    assert(tonumber(after.FireResist) >= -40)
    assert(tonumber(after.ColdResist) >= -40)
    assert(tonumber(after.BlockChance) >= 24)

    print("IMPLICIT GEAR CALCULATION: PASS")

    local xml = assert(build:SaveDB("QUIN_Implicit_Gear_v1.xml"))

    print("QUIN_XML_BEGIN")
    io.write(xml)
    io.write("\n")
    print("QUIN_XML_END")
end

local ok, err = pcall(run)

if not ok then
    io.stderr:write(
        "QUIN_IMPLICIT_ERROR:" .. tostring(err) .. "\n"
    )
    os.exit(1)
end
