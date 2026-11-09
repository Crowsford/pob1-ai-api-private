
-- PoE BuildLab AI — Rare Item Roundtrip Probe v1
-- Read-only. Does not modify the original build.

package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local function readFile(path)
    local file, err = io.open(path, "rb")
    assert(file, err)
    local data = file:read("*a")
    file:close()
    return data
end

local function run()
    local xmlPath = assert(arg[1], "Build XML required")

    dofile("HeadlessWrapper.lua")
    loadBuildFromXML(readFile(xmlPath), "Rare Item Probe")

    local itemsTab = assert(build.itemsTab)
    local slot = assert(itemsTab.slots["Weapon 1"])
    local original = assert(itemsTab.items[slot.selItemId])

    assert(original.rarity == "RARE",
        "Original weapon is not rare")

    print("=== ORIGINAL RARE ITEM ===")
    print("Name:", original.name)
    print("Base:", original.baseName)
    print("Type:", original.base.type)
    print("Rarity:", original.rarity)

    local raw = original:BuildRaw()

    print("=== ORIGINAL RAW ===")
    print(raw)

    local clone = new("Item", raw)

    assert(clone.base, "Clone base not recognized")
    assert(clone.rarity == "RARE", "Clone rarity mismatch")

    clone:BuildModList()

    print("=== RARE ROUNDTRIP ===")
    print("Clone name:", clone.name)
    print("Clone base:", clone.baseName)
    print("Clone type:", clone.base.type)
    print("Clone rarity:", clone.rarity)

    print("Original explicit mods:",
        #(original.explicitModLines or {}))
    print("Clone explicit mods:",
        #(clone.explicitModLines or {}))

    print("Original implicit mods:",
        #(original.implicitModLines or {}))
    print("Clone implicit mods:",
        #(clone.implicitModLines or {}))

    print("Independent object:",
        tostring(original ~= clone))

    print("Original slot unchanged:",
        tostring(itemsTab.items[slot.selItemId] == original))

    print("Source XML written: NO")
    print("Affix legality verified: NO")
    print("Result: PASS")
end

local ok, err = pcall(run)

if not ok then
    io.stderr:write("RARE_PROBE_ERROR:" .. tostring(err) .. "\n")
    os.exit(1)
end
