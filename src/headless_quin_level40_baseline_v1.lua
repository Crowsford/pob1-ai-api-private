package.path="../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath="../runtime/?.dll;" .. package.cpath

local xmlPath=assert(arg[1])

local function readFile(p)
    local f=assert(io.open(p,"rb"))
    local s=f:read("*a")
    f:close()
    return s
end

local function run()
    dofile("HeadlessWrapper.lua")
    loadBuildFromXML(readFile(xmlPath),"QUIN Level 40 Baseline")

    local spec=assert(build.spec)

    print("=== QUIN LEVEL 40 BASELINE ===")
    print("LEVEL:",build.characterLevel)
    print("CLASS:",spec.curClassName)
    print("ASCENDANCY:",spec.curAscendClassName)

    local normal,ascend,secondary,sockets=spec:CountAllocNodes()

    print("NORMAL POINTS:",normal)
    print("ASCENDANCY POINTS:",ascend)
    print("SECONDARY ASCENDANCY:",secondary)
    print("SOCKETS:",sockets)

    print("")
    print("=== ALLOCATED NODES ===")

    local nodes={}
    for id,node in pairs(spec.allocNodes) do
        nodes[#nodes+1]={
            id=id,
            name=node.name or "?",
            kind=node.type or "?",
            ascend=node.ascendancyName or ""
        }
    end

    table.sort(nodes,function(a,b)
        return tostring(a.id)<tostring(b.id)
    end)

    for _,node in ipairs(nodes) do
        print(
            "NODE:",
            node.id,
            "|",node.name,
            "| TYPE:",node.kind,
            "| ASC:",node.ascend
        )
    end

    print("")
    print("=== GEM DATABASE ===")

    local gems=assert(dofile("Data/Gems.lua"))

    local names={
        "Storm Brand",
        "Added Lightning Damage Support",
        "Controlled Destruction Support",
        "Faster Casting Support",
        "Lightning Penetration Support",
        "Concentrated Effect Support"
    }

    for _,name in ipairs(names) do
        local matches={}

        for id,gem in pairs(gems) do
            if gem.name==name then
                matches[#matches+1]={id=id,gem=gem}
            end
        end

        print("")
        print("GEM:",name)
        print("MATCHES:",#matches)

        for _,entry in ipairs(matches) do
            print("ID:",entry.id)

            for _,field in ipairs({
                "name","gameId","variantId",
                "grantedEffectId","naturalMaxLevel"
            }) do
                print(
                    field..":",
                    tostring(entry.gem[field])
                )
            end

            for key,value in pairs(entry.gem) do
                if type(value)=="number" and (
                    tostring(key):lower():find("level")
                    or tostring(key):lower():find("require")
                ) then
                    print("LEVEL FIELD:",key,value)
                end
            end
        end
    end

    print("")
    print("BASELINE DISCOVERY: COMPLETE")
    print("XML EXPORTED: NO")
end

local ok,err=pcall(run)
if not ok then
    io.stderr:write("QUIN_BASELINE_ERROR:"..tostring(err).."\n")
    os.exit(1)
end
