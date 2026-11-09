
package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local xmlPath = assert(arg[1])
local json = require("dkjson")

local function readFile(path)
    local f = assert(io.open(path, "rb"))
    local s = f:read("*a")
    f:close()
    return s
end

dofile("HeadlessWrapper.lua")
loadBuildFromXML(readFile(xmlPath), "QUIN Passive Decision")

local spec = assert(build.spec)
assert(spec.curClassName == "Templar")
assert(spec.curAscendClassName == "Inquisitor")
assert(spec.treeVersion == "3_29")
assert(build.characterLevel == 40)

local spent = spec:CountAllocNodes()
assert(spent == 8)

local candidates = {}

for id, node in pairs(spec.nodes) do
    if (node.type == "Normal" or node.type == "Notable")
        and not node.alloc
        and not node.ascendancyName
        and not node.isMultipleChoiceOption
        and node.path then

        local cost = 0
        local path = {}

        for _, step in ipairs(node.path) do
            if not step.alloc then
                cost = cost + 1
                path[#path + 1] = step.id
            end
        end

        if cost >= 1 and cost <= 12 then
            local stats = table.concat(node.sd or {}, " | ")
            local lower = stats:lower()
            local name = tostring(node.dn or node.name or "")

            local category

            if lower:find("minion", 1, true) then
                category = nil
            elseif lower:find("maximum life", 1, true) then
                category = "LIFE"
            elseif lower:find("block spell damage", 1, true) then
                category = "SPELL_BLOCK"
            elseif lower:find("brand", 1, true) then
                category = "BRAND"
            elseif lower:find("lightning damage", 1, true) then
                category = "LIGHTNING"
            elseif lower:find("cast speed", 1, true) then
                category = "CAST_SPEED"
            elseif lower:find("spell damage", 1, true) then
                category = "SPELL_DAMAGE"
            elseif lower:find("elemental resistances", 1, true) then
                category = "RESISTANCE"
            end

            if category then
                candidates[#candidates + 1] = {
                    id = id,
                    name = name,
                    type = node.type,
                    category = category,
                    cost = cost,
                    stats = node.sd or {},
                    path = path
                }
            end
        end
    end
end

table.sort(candidates, function(a, b)
    if a.cost ~= b.cost then return a.cost < b.cost end
    return a.id < b.id
end)

local selected = {}
local counts = {}

for _, node in ipairs(candidates) do
    local count = counts[node.category] or 0
    if count < 8 then
        selected[#selected + 1] = node
        counts[node.category] = count + 1
    end
end

print("QUIN_CATALOG_JSON:" .. json.encode({
    className = spec.curClassName,
    ascendancy = spec.curAscendClassName,
    level = build.characterLevel,
    spentPoints = spent,
    remainingBudget = 31,
    candidates = selected
}))
