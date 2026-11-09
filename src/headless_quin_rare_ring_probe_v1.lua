package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
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

local function checkAffix(mods, id, tags, itemLevel, kind, group)
    local mod = assert(mods[id], "Unknown affix: " .. id)

    assert(mod.type == kind, "Wrong affix type")
    assert(mod.group == group, "Wrong affix group")
    assert(mod.level <= itemLevel, "Affix level too high")

    print("")
    print("AFFIX:", id)
    print("TYPE:", mod.type)
    print("GROUP:", mod.group)
    print("LEVEL:", mod.level)

    local selectedKey, selectedWeight

    for i, key in ipairs(mod.weightKey or {}) do
        local weight = (mod.weightVal or {})[i] or 0

        if tags[key] then
            print("MATCH:", key, "WEIGHT:", weight)

            if not selectedKey then
                selectedKey = key
                selectedWeight = weight
            end
        end
    end

    print("FIRST MATCH:", tostring(selectedKey))
    print("FIRST WEIGHT:", tostring(selectedWeight))

    assert(selectedKey, "No matching generation tag")
    assert(selectedWeight > 0, "Affix blocked by first matching tag")

    return mod
end

local function run()
    dofile("HeadlessWrapper.lua")

    loadBuildFromXML(readFile(xmlPath), "QUIN Rare Ring Probe")

    assert(build.spec.curClassName == "Templar")
    assert(build.spec.curAscendClassName == "Inquisitor")
    assert(build.characterLevel == 40)
    assert(build.spec:CountAllocNodes() == 8)

    local mods = assert(dofile("Data/ModExplicit.lua"))

    local tab = assert(build.itemsTab)
    local slot = assert(tab.slots["Ring 1"])
    local oldId = assert(slot.selItemId)
    local oldItem = assert(tab.items[oldId])

    assert(oldItem.baseName == "Ruby Ring")
    assert(oldItem:BuildRaw():find("+20%% to Fire Resistance"))

    local itemLevel = 40
    local tags = assert(oldItem.base.tags)

    print("=== QUIN RARE RING PREFLIGHT ===")
    print("BASE:", oldItem.baseName)
    print("ITEM LEVEL:", itemLevel)

    local lifeMod = checkAffix(
        mods, "IncreasedLife5", tags,
        itemLevel, "Prefix", "IncreasedLife"
    )

    local lightningMod = checkAffix(
        mods, "LightningResist4", tags,
        itemLevel, "Suffix", "LightningResistance"
    )

    assert(lifeMod.group ~= lightningMod.group)

    print("")
    print("PRELIMINARY AFFIX ELIGIBILITY: PASS")

    local before = calculate()

    local raw = table.concat({
        "Rarity: RARE",
        "QUIN Test Ring",
        "Ruby Ring",
        "Item Level: 40",
        "Implicits: 1",
        "+20% to Fire Resistance",
        "+70 to maximum Life",
        "+24% to Lightning Resistance"
    }, "\n")

    local item = new("Item", raw)

    assert(item.base, "Item base missing")
    assert(item.baseName == "Ruby Ring")
    assert(tab:IsItemValidForSlot(item, "Ring 1"))

    local parsed = item:BuildRaw()

    print("")
    print("=== GENERATED RARE RING ===")
    print(parsed)

    for _, expected in ipairs({
        "Ruby Ring",
        "+20% to Fire Resistance",
        "+70 to maximum Life",
        "+24% to Lightning Resistance"
    }) do
        assert(parsed:find(expected, 1, true),
            "Missing modifier: " .. expected)
    end

    item.id = oldId
    tab:AddItem(item, true)
    assert(tab.items[oldId] == item)
    assert(slot.selItemId == oldId)

    tab:PopulateSlots()

    local after = calculate()

    print("")
    print("=== POB MEASUREMENT ===")

    for _, key in ipairs({
        "Life", "FireResist", "ColdResist",
        "LightningResist", "EnergyShield",
        "CombinedDPS", "TotalEHP"
    }) do
        print(
            key .. ":",
            tostring(before[key]),
            "->",
            tostring(after[key])
        )
    end

    assert(tonumber(after.Life) > tonumber(before.Life))
    assert(tonumber(after.LightningResist) >
           tonumber(before.LightningResist))

    print("")
    print("POB RARE RING CALCULATION: PASS")
    print("FULL MOD VALIDATION: NOT YET VERIFIED")
    print("CRAFTING AVAILABILITY: NOT VERIFIED")
    print("XML EXPORTED: NO")
    print("ORIGINAL BUILD MODIFIED: NO")
end

local ok, err = pcall(run)

if not ok then
    io.stderr:write(
        "QUIN_RARE_RING_ERROR:" .. tostring(err) .. "\n"
    )
    os.exit(1)
end
