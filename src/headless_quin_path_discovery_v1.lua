-- QUIN Passive Path Discovery v1
-- Read-only investigation of the PoB 3.29 passive tree.

package.path =
    "../runtime/lua/?.lua;../runtime/lua/?/init.lua;"
    .. package.path

package.cpath = "../runtime/?.dll;" .. package.cpath

-- Capture argument BEFORE PoB initialization.
local xmlPath = assert(arg[1], "Missing XML argument")

local function readFile(filename)
    local f, err = io.open(filename, "rb")
    assert(f, err)
    local data = f:read("*a")
    f:close()
    return data
end

local function run()
    dofile("HeadlessWrapper.lua")

    loadBuildFromXML(
        readFile(xmlPath),
        "QUIN Path Discovery"
    )

    local spec = assert(build.spec)

    assert(spec.curClassName == "Templar")
    assert(spec.curAscendClassName == "Inquisitor")
    assert(spec.treeVersion == "3_29")
    assert(build.characterLevel == 40)

    local candidates = {}

    for id, node in pairs(spec.nodes) do
        if node.type == "Normal"
            and not node.ascendancyName
            and not node.alloc
            and node.path
            and not node.isMultipleChoiceOption then

            local cost = 0

            for _, step in ipairs(node.path) do
                if not step.alloc then
                    cost = cost + 1
                end
            end

            if cost >= 1 and cost <= 15 then
                local stats = table.concat(node.sd or {}, " | ")
                local lower = stats:lower()
                local name = tostring(
                    node.dn or node.name or ""
                )

                local category = nil

                if lower:find("to intelligence", 1, true) then
                    category = "INTELLIGENCE"
                elseif lower:find("maximum life", 1, true) then
                    category = "LIFE"
                elseif lower:find("lightning damage", 1, true) then
                    category = "LIGHTNING"
                elseif lower:find("spell damage", 1, true) then
                    category = "SPELL"
                end

                if category then
                    candidates[#candidates + 1] = {
                        id = id,
                        cost = cost,
                        category = category,
                        name = name,
                        stats = stats
                    }
                end
            end
        end
    end

    table.sort(candidates, function(a, b)
        if a.cost ~= b.cost then
            return a.cost < b.cost
        end

        return a.id < b.id
    end)

    print("=== QUIN PASSIVE PATH DISCOVERY ===")
    print("Class:", spec.curClassName)
    print("Tree:", spec.treeVersion)
    print("Candidates within 15 points:", #candidates)

    local printed = 0
    local perCategory = {}

    for _, node in ipairs(candidates) do
        local count = perCategory[node.category] or 0

        if count < 8 then
            print(
                "NODE:", node.id,
                "| COST:", node.cost,
                "| CATEGORY:", node.category,
                "| NAME:", node.name,
                "| STATS:", node.stats
            )

            perCategory[node.category] = count + 1
            printed = printed + 1
        end
    end

    print("PRINTED:", printed)
    print("DISCOVERY: COMPLETE")
    print("FILES MODIFIED: NO")
end

local ok, err = pcall(run)

if not ok then
    io.stderr:write(
        "PATH_DISCOVERY_ERROR:"
        .. tostring(err) .. "\n"
    )
    os.exit(1)
end
