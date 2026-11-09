local mods = dofile("Data/ModExplicit.lua")
local tiers = {}

for id, mod in pairs(mods) do
    if id:match("^StaffSpellBlockPercentage%d+$")
        and mod.type == "Suffix"
        and mod.group == "AdditionalSpellBlock" then

        local low, high = mod[1]:match("%((%d+)%-(%d+)%)")
        local weight = 0

        for i, key in ipairs(mod.weightKey or {}) do
            if key == "staff" then
                weight = mod.weightVal[i] or 0
            end
        end

        if low and high and weight > 0 then
            tiers[#tiers + 1] = {
                id = id,
                low = tonumber(low),
                high = tonumber(high),
                level = mod.level,
                weight = weight
            }
        end
    end
end

table.sort(tiers, function(a, b) return a.high < b.high end)

for _, tier in ipairs(tiers) do
    print(string.format("TIER|%s|%d|%d|%d|%d",
        tier.id, tier.low, tier.high, tier.level, tier.weight))
end
