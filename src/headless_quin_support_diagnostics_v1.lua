
package.path="../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath="../runtime/?.dll;" .. package.cpath

local xmlPath=assert(arg[1])

local function readFile(p)
    local f=assert(io.open(p,"rb"))
    local data=f:read("*a")
    f:close()
    return data
end

local function run()
    dofile("HeadlessWrapper.lua")
    loadBuildFromXML(readFile(xmlPath),"QUIN Support Diagnostics")

    wipeGlobalCache()
    build.outputRevision=build.outputRevision+1
    build.buildFlag=false
    build.skillsTab:UpdateSocketGroups()
    build.calcsTab:BuildOutput()

    local output=assert(build.calcsTab.mainOutput)

    print("=== MAIN OUTPUT ===")

    local keys={}
    for key in pairs(output) do
        if type(key)=="string" then
            local k=key:lower()
            if k:find("mana",1,true)
                or k:find("duration",1,true)
                or k:find("brand",1,true)
                or k:find("cast",1,true)
                or k:find("activ",1,true)
                or k:find("dps",1,true)
                or k:find("penetr",1,true)
                or k:find("skill",1,true) then
                keys[#keys+1]=key
            end
        end
    end

    table.sort(keys)

    for _,key in ipairs(keys) do
        if type(output[key])~="table" then
            print("STAT:",key,"=",tostring(output[key]))
        end
    end

    print("=== MAIN SKILL ===")
    local mainSkill=build.calcsTab.mainSkill
    print("MAIN SKILL AVAILABLE:",tostring(mainSkill~=nil))

    if mainSkill then
        for key,value in pairs(mainSkill) do
            if type(key)=="string" and (
                key:lower():find("name",1,true)
                or key:lower():find("skill",1,true)
            ) and type(value)~="table" then
                print("SKILL FIELD:",key,tostring(value))
            end
        end
    end

    print("DIAGNOSTIC: COMPLETE")
end

local ok,err=pcall(run)
if not ok then
    io.stderr:write("QUIN_ERROR:"..tostring(err).."\n")
    os.exit(1)
end
