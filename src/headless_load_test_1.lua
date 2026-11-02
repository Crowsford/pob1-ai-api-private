package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath = "../runtime/?.dll;" .. package.cpath

dofile("HeadlessWrapper.lua")

local path = os.getenv("USERPROFILE")
    .. "\\Documents\\Path of Building\\Builds\\1.xml"

local file, err = io.open(path, "rb")
assert(file, err)

local xml = file:read("*a")
file:close()

print("Loading BabaBan...")
loadBuildFromXML(xml, "BabaBan Headless Test")

print("=== INIT STATUS ===")
print("Mode:", tostring(main.mode))
print("Pending mode:", tostring(main.newMode))
print("Target version:", tostring(build.targetVersion))
print("XML sections:", build.xmlSectionList and #build.xmlSectionList or "nil")
print("Tree tab exists:", build.treeTab ~= nil)
print("Spec exists:", build.spec ~= nil)
print("Calcs tab exists:", build.calcsTab ~= nil)
print("Popup count:", main.popups and #main.popups or "nil")

print("=== MODE TRANSITION TEST ===")

for i = 1, 10 do
    print(
        "Before frame", i,
        "mode:", tostring(main.mode),
        "newMode:", tostring(main.newMode)
    )

    runCallback("OnFrame")

    print(
        "After frame", i,
        "mode:", tostring(main.mode),
        "newMode:", tostring(main.newMode),
        "hasOutput:", tostring(build.calcsTab and build.calcsTab.mainOutput ~= nil)
    )
end

assert(build and build.spec, "Build not initialized")
assert(build.calcsTab, "CalcsTab not initialized")

print("=== BUILD DIAGNOSTICS ===")
print("Build name:", build.buildName)
print("Build level:", build.characterLevel)
print("Class:", build.spec.curClassName)
print("Ascendancy:", build.spec.curAscendClassName)
print("Main output exists:", build.calcsTab.mainOutput ~= nil)
print("Current mode:", main and main.mode)

if not build.calcsTab.mainOutput then
    print("Trying one additional OnFrame...")
    runCallback("OnFrame")
end

print("Main output after frame:", build.calcsTab.mainOutput ~= nil)

local output = assert(build.calcsTab.mainOutput, "No calculation output")

print("=== HEADLESS BUILD LOADED ===")
print("Name:", build.buildName)
print("Class:", build.spec.curClassName)
print("Ascendancy:", build.spec.curAscendClassName)
print("Level:", build.characterLevel)
print("Life:", output.Life)
print("Mana:", output.Mana)
print("Total DPS:", output.TotalDPS)
print("Full DPS:", output.FullDPS)
print("Total EHP:", output.TotalEHP)