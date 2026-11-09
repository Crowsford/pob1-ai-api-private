local mods = dofile("Data/ModExplicit.lua")
local result = {}
for id, mod in pairs(mods) do
    if id:match("^ChaosDamageOverTimeMultiplierTwoHand%d+_+$") then
        local minVal, maxVal = mod[1]:match("%((%d+)%-(%d+)%)")
        local weight = 0
        for i, key in ipairs(mod.weightKey or {}) do
            if key == "staff" then weight = mod.weightVal[i] or 0 end
        end
        if minVal and maxVal and mod.type == "Suffix" then
            result[#result + 1] = {
                id = id, min = tonumber(minVal), max = tonumber(maxVal),
                level = mod.level, weight = weight
            }
        end
    end
end
table.sort(result, function(a, b) return a.min < b.min end)
print("=== STAFF CHAOS DOT MULTIPLIER TIERS ===")
for _, m in ipairs(result) do
    print(string.format("%-52s %2d-%2d%%  ilvl=%2d  weight=%d",
        m.id, m.min, m.max, m.level, m.weight))
end
print("Total tiers:", #result)
