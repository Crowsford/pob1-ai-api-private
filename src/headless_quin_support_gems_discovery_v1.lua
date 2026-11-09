package.path="../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
package.cpath="../runtime/?.dll;" .. package.cpath

local function run()
    dofile("HeadlessWrapper.lua")

    local gems=assert(dofile("Data/Gems.lua"))

    local searches={
        "Storm Brand",
        "Added Lightning",
        "Controlled Destruction",
        "Faster Casting",
        "Lightning Penetration",
        "Concentrated Effect",
        "Swiftbrand",
        "Inspiration",
        "Elemental Focus"
    }

    print("=== QUIN SUPPORT GEM DISCOVERY V1 ===")

    for _,needle in ipairs(searches) do
        print("")
        print("=== SEARCH:",needle,"===")

        local matches={}

        for id,gem in pairs(gems) do
            local name=tostring(gem.name or "")
            local base=tostring(gem.baseTypeName or "")
            local effect=tostring(gem.grantedEffectId or "")

            if name:lower():find(needle:lower(),1,true)
                or base:lower():find(needle:lower(),1,true)
                or effect:lower():find(
                    needle:gsub(" ",""):lower(),1,true
                ) then

                matches[#matches+1]={id=id,gem=gem}
            end
        end

        table.sort(matches,function(a,b)
            return a.id<b.id
        end)

        print("MATCHES:",#matches)

        for _,entry in ipairs(matches) do
            local gem=entry.gem

            print("")
            print("ID:",entry.id)
            print("NAME:",tostring(gem.name))
            print("BASE:",tostring(gem.baseTypeName))
            print("EFFECT:",tostring(gem.grantedEffectId))
            print("VARIANT:",tostring(gem.variantId))

            print("FIELDS:")

            local keys={}
            for key in pairs(gem) do
                keys[#keys+1]=key
            end

            table.sort(keys,function(a,b)
                return tostring(a)<tostring(b)
            end)

            for _,key in ipairs(keys) do
                local value=gem[key]

                if type(value)=="table" then
                    local count=0
                    for _ in pairs(value) do count=count+1 end
                    print(" ",key,"= TABLE ("..count..")")
                else
                    print(" ",key,"=",tostring(value))
                end
            end
        end
    end

    print("")
    print("DISCOVERY: COMPLETE")
    print("FILES MODIFIED: NO")
end

local ok,err=pcall(run)
if not ok then
    io.stderr:write(
        "QUIN_GEM_ERROR:"..tostring(err).."\n"
    )
    os.exit(1)
end
