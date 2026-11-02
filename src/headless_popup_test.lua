package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

dofile("HeadlessWrapper.lua")

local path = os.getenv("USERPROFILE")
    .. "\\Documents\\Path of Building\\Builds\\1.xml"

local file = assert(io.open(path, "rb"))
local xml = file:read("*a")
file:close()

loadBuildFromXML(xml, "Popup Diagnostic")

print("Mode:", tostring(main.mode))
print("Popup count:", #main.popups)

for i, popup in ipairs(main.popups) do
    print("=== POPUP " .. i .. " ===")
    print("Type:", type(popup))

    for k, v in pairs(popup) do
        if type(v) == "string" or type(v) == "number" or type(v) == "boolean" then
            print(tostring(k), tostring(v):sub(1, 500))
        end
    end
end

print("Launch prompt:", tostring(launch.promptMsg))
print("Build target version:", tostring(build.targetVersion))
print("Output exists:", tostring(build.calcsTab.mainOutput ~= nil))