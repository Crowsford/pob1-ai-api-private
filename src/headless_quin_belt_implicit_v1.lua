
package.path =
    "../runtime/lua/?.lua;../runtime/lua/?/init.lua;"
    .. package.path
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
    loadBuildFromXML(readFile(xmlPath), "QUIN Belt Implicit")

    assert(build.spec.curClassName == "Templar")
    assert(build.spec.curAscendClassName == "Inquisitor")
    assert(build.characterLevel == 40)
    assert(build.spec:CountAllocNodes() == 8)

    local tab = assert(build.itemsTab)
    local beltSlot = assert(tab.slots["Belt"])

    local oldId = beltSlot.selItemId
    assert(oldId and oldId ~= 0)

    local oldItem = assert(tab.items[oldId])
    assert(oldItem.baseName == "Leather Belt")

    local before = calculate()
    local beforeLife = assert(tonumber(before.Life))

    print("=== BEFORE ===")
    print("Belt ID:", oldId)
    print("Life:", beforeLife)
    print("Belt raw:")
    print(oldItem:BuildRaw())

    -- Replace the item at the SAME ID and slot.
    -- Minimum database implicit roll: +25 Life.
    local raw = table.concat({
        "Rarity: NORMAL",
        "Leather Belt",
        "LevelReq: 8",
        "Implicits: 1",
        "+25 to maximum Life"
    }, "\n")

    local newItem = new("Item", raw)

    assert(newItem.base, "Item base missing")
    assert(newItem.baseName == "Leather Belt")

    assert(
        tab:IsItemValidForSlot(newItem, "Belt"),
        "Invalid belt slot"
    )

    local req = newItem.base.req or {}

    assert((req.level or 0) <= build.characterLevel)

    -- Preserve the existing item ID.
    newItem.id = oldId
    tab:AddItem(newItem, true)

    assert(tab.items[oldId] == newItem)
    assert(beltSlot.selItemId == oldId)

    tab:PopulateSlots()

    local after = calculate()
    local afterLife = assert(tonumber(after.Life))
    local lifeGain = afterLife - beforeLife

    print("")
    print("=== AFTER ===")
    print("Belt ID:", beltSlot.selItemId)
    print("Life:", afterLife)
    print("Life Gain:", lifeGain)
    print("Belt raw:")
    print(newItem:BuildRaw())

    assert(lifeGain == 25,
        "Expected exactly +25 Life from belt implicit")

    print("BELT IMPLICIT CALCULATION: PASS")

    local xml = assert(build:SaveDB("QUIN_Belt_Implicit_v1.xml"))
    assert(type(xml) == "string" and #xml > 100)

    print("QUIN_XML_BEGIN")
    io.write(xml)
    io.write("\n")
    print("QUIN_XML_END")
end

local ok, err = pcall(run)

if not ok then
    io.stderr:write(
        "QUIN_BELT_ERROR:" .. tostring(err) .. "\n"
    )
    os.exit(1)
end
