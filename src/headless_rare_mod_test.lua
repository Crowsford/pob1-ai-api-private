
-- PoE BuildLab AI — Rare Modifier Experiment v1
-- Read-only. Test one numerical modifier change.
-- Does not verify crafting legality.

package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local function readFile(path)
    local file, err = io.open(path, "rb")
    assert(file, err)
    local content = file:read("*a")
    file:close()
    return content
end

local function run()
    local xmlPath = assert(arg[1], "Build XML required")
    local groupIndex = tonumber(arg[2] or "6")

    dofile("HeadlessWrapper.lua")
    loadBuildFromXML(readFile(xmlPath), "Rare Modifier Test")

    local itemsTab = assert(build.itemsTab)
    local slot = assert(itemsTab.slots["Weapon 1"])
    local original = assert(itemsTab.items[slot.selItemId])

    assert(original.rarity == "RARE")
    assert(original.base.type == "Staff")

    local group = assert(
        build.skillsTab.socketGroupList[groupIndex]
    )

    assert(group.enabled and group.slotEnabled)
    assert(group.gemList and #group.gemList > 0)

    -- Select the intended damage skill.
    build.mainSocketGroup = groupIndex

    wipeGlobalCache()
    build.outputRevision = build.outputRevision + 1
    build.buildFlag = false
    build.skillsTab:UpdateSocketGroups()
    build.calcsTab:BuildOutput()

    assert(build.mainSocketGroup == groupIndex)

    local calcFunc, calcBase =
        build.calcsTab:GetMiscCalculator()

    assert(type(calcFunc) == "function")

    local baseline = calcBase or calcFunc({})

    -- Create an independent copy.
    local raw = original:BuildRaw()

    local oldMod =
        "+43% to Chaos Damage over Time Multiplier"

    local newMod =
        "+44% to Chaos Damage over Time Multiplier"

    local startPos, endPos =
        raw:find(oldMod, 1, true)

    assert(startPos, "Expected original modifier missing")

    assert(
        not raw:find(oldMod, endPos + 1, true),
        "Original modifier appears multiple times"
    )

    local changedRaw =
        raw:sub(1, startPos - 1)
        .. newMod
        .. raw:sub(endPos + 1)

    -- Control: unchanged copy must reproduce baseline.
    local unchanged = new("Item", raw)
    assert(unchanged.base)
    unchanged:BuildModList()

    local control = calcFunc({
        repSlotName = "Weapon 1",
        repItem = unchanged,
    })

    -- Experimental candidate with one changed modifier.
    local candidate = new("Item", changedRaw)

    assert(candidate.base, "Candidate base missing")
    assert(candidate.rarity == "RARE")
    assert(candidate.base.type == original.base.type)

    candidate:BuildModList()

    local modified = calcFunc({
        repSlotName = "Weapon 1",
        repItem = candidate,
    })

    local metrics = {
        "CombinedDPS",
        "TotalDot",
        "TotalEHP",
        "EnergyShield",
        "PhysicalMaximumHitTaken",
    }

    print("=== RARE MODIFIER EXPERIMENT ===")
    print("Skill group:", groupIndex)
    print("Skill ID:", group.gemList[1].skillId)
    print("Original item:", original.name)
    print("Changed modifier:")
    print("  Before:", oldMod)
    print("  After: ", newMod)

    print("=== NO-OP CONTROL ===")

    local mismatches = 0

    for _, key in ipairs(metrics) do
        local a = baseline[key]
        local b = control[key]

        if type(a) ~= "number" or
           type(b) ~= "number" then
            error("Missing numeric control stat: " .. key)
        end

        if math.abs(a - b) >
           0.000001 * math.max(1, math.abs(a)) then
            mismatches = mismatches + 1
            print("MISMATCH:", key, a, b)
        end
    end

    print("Mismatches:", mismatches)

    assert(mismatches == 0, "NO_OP_FAILED")

    print("=== NUMERIC CHANGES ===")

    for _, key in ipairs(metrics) do
        local before = baseline[key]
        local after = modified[key]

        assert(
            type(before) == "number" and
            type(after) == "number",
            "Missing numeric stat: " .. key
        )

        local delta = after - before

        local percent =
            before ~= 0 and delta / before * 100 or nil

        print(
            key,
            string.format("%.2f -> %.2f", before, after),
            percent and string.format("%+.4f%%", percent)
                or "N/A"
        )
    end

    assert(
        itemsTab.items[slot.selItemId] == original,
        "Original equipment changed"
    )

    print("Original equipment preserved: YES")
    print("Source XML written: NO")
    print("Affix legality verified: NO")
    print("Result: PASS")
end

local ok, err = pcall(run)

if not ok then
    io.stderr:write(
        "RARE_MOD_TEST_ERROR:" .. tostring(err) .. "\n"
    )
    os.exit(1)
end
