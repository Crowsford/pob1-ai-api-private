
package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

local xmlPath = assert(arg[1], "XML path required")

dofile("HeadlessWrapper.lua")
local file = assert(io.open(xmlPath, "rb"))
local xml = file:read("*a")
file:close()

loadBuildFromXML(xml, "Output Inspection")

assert(main.mode == "BUILD", "Build not loaded")

local output = assert(
    build.calcsTab.mainOutput,
    "Calculation output unavailable"
)

local keys = {}

for key, value in pairs(output) do
    if type(value) == "number" then
        keys[#keys + 1] = key
    end
end

table.sort(keys)

print("=== NUMERIC OUTPUT FIELDS ===")
print("Total numeric fields:", #keys)

for _, key in ipairs(keys) do
    print(key .. " = " .. tostring(output[key]))
end
