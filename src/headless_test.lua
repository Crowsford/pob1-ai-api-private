package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

dofile("HeadlessWrapper.lua")

print("Creating headless build...")
newBuild()

if not build or not build.calcsTab then
    error("Build or calculation module not initialized")
end

local output = build.calcsTab.mainOutput

if type(output) ~= "table" then
    error("Calculation output is unavailable")
end

print("HEADLESS CALCULATION SUCCESS")
print("Level:", build.characterLevel)
print("Class:", build.spec.curClassName)
print("Life:", output.Life)
print("Mana:", output.Mana)
print("Total DPS:", output.TotalDPS)
print("Total EHP:", output.TotalEHP)