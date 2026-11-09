-- QUIN Affix Eligibility Discovery V1
-- Read-only: no changes to PoB or character XML.

package.path =
    "../runtime/lua/?.lua;../runtime/lua/?/init.lua;"
    .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local function run()
    dofile("HeadlessWrapper.lua")

    local mods = assert(
        dofile("Data/ModExplicit.lua"),
        "ModExplicit database unavailable"
    )

    local ring = new(
        "Item",
        "Rarity: NORMAL\nRuby Ring\nItem Level: 40\nImplicits: 0"
    )

    assert(ring.base, "Ruby Ring base not found")
    assert(ring.type == "Ring")

    local itemLevel = 40
    local tags = ring.base.tags or {}

    print("=== QUIN AFFIX ELIGIBILITY V1 ===")
    print("BASE:", ring.baseName)
    print("ITEM TYPE:", ring.type)
    print("ITEM LEVEL:", itemLevel)

    print("")
    print("=== ITEM BASE TAGS ===")

    local tagNames = {}

    for tag, enabled in pairs(tags) do
        if enabled then
            tagNames[#tagNames + 1] = tostring(tag)
        end
    end

    table.sort(tagNames)

    for _, tag in ipairs(tagNames) do
        print("TAG:", tag)
    end

    print("")
    print("=== RELEVANT MODIFIERS ===")

    local prefixes = 0
    local suffixes = 0
    local candidates = {}

    for id, mod in pairs(mods) do
        local group = tostring(mod.group or "")

        if group == "IncreasedLife"
            or group == "LightningResistance"
            or group == "FireResistance"
            or group == "ColdResistance" then

            local requiredLevel = tonumber(mod.level) or 999
            local keys = mod.weightKey or {}
            local values = mod.weightVal or {}

            if requiredLevel <= itemLevel then
                local matches = {}

                for i, key in ipairs(keys) do
                    if key == "ring" or tags[key] then
                        matches[#matches + 1] = {
                            key = key,
                            weight = values[i] or 0,
                            position = i
                        }
                    end
                end

                if #matches > 0 then
                    candidates[#candidates + 1] = {
                        id = id,
                        mod = mod,
                        matches = matches
                    }
                end
            end
        end
    end

    table.sort(candidates, function(a, b)
        if a.mod.group ~= b.mod.group then
            return a.mod.group < b.mod.group
        end
        if a.mod.level ~= b.mod.level then
            return a.mod.level < b.mod.level
        end
        return a.id < b.id
    end)

    for _, entry in ipairs(candidates) do
        local mod = entry.mod

        print("")
        print("MOD ID:", entry.id)
        print("TYPE:", tostring(mod.type))
        print("GROUP:", tostring(mod.group))
        print("REQUIRED ITEM LEVEL:", tostring(mod.level))

        for i, line in ipairs(mod) do
            print("STAT " .. i .. ":", tostring(line))
        end

        for _, match in ipairs(entry.matches) do
            print(
                "MATCH:",
                match.key,
                "| WEIGHT:", match.weight,
                "| POSITION:", match.position
            )
        end

        if mod.type == "Prefix" then
            prefixes = prefixes + 1
        elseif mod.type == "Suffix" then
            suffixes = suffixes + 1
        end
    end

    print("")
    print("=== SUMMARY ===")
    print("MATCHING MODIFIERS:", #candidates)
    print("PREFIXES:", prefixes)
    print("SUFFIXES:", suffixes)
    print("WEIGHT PRECEDENCE VERIFIED: NO")
    print("AFFIX COMBINATION VERIFIED: NO")
    print("ITEM CREATED: NO")
    print("FILES MODIFIED: NO")
    print("DISCOVERY: COMPLETE")
end

local ok, err = pcall(run)

if not ok then
    io.stderr:write(
        "QUIN_AFFIX_ERROR:" .. tostring(err) .. "\n"
    )
    os.exit(1)
end
