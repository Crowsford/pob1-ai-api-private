local Routes = {}

local function json_escape(s)
  s = tostring(s)
  s = s:gsub("\\", "\\\\"):gsub('"', '\\"'):gsub("\r", "\\r"):gsub("\n", "\\n")
  return s
end

local function json_kv(k, v)
  if v == nil then return '"'..k..'":null' end
  local t = type(v)
  if t == "number" or t == "boolean" then
    return '"'..k..'":'..tostring(v)
  else
    return '"'..k..'":"'..json_escape(v)..'"'
  end
end

local function json_obj(tbl)
  local parts = {}
  for k,v in pairs(tbl) do
    parts[#parts+1] = json_kv(k, v)
  end
  return "{"..table.concat(parts, ",").."}"
end

-- ctx getter: мы не хотим жёстко привязываться, поэтому пробуем вытащить build из main
local function first_build_in(obj)
  if type(obj) ~= "table" then return nil end
  if obj.build then return obj.build end
  if obj.activeBuild then return obj.activeBuild end
  if obj.builds and obj.selBuild and obj.builds[obj.selBuild] then return obj.builds[obj.selBuild] end
  if obj.builds and type(obj.builds) == "table" then
    -- иногда builds - список
    for _, b in pairs(obj.builds) do
      if type(b) == "table" and (b.output or b.spec or b.skillsTab or b.treeTab) then
        return b
      end
    end
  end
  return nil
end

local function get_active_build()
  local main = _G.PoBAI and _G.PoBAI.pobMain
  if not main then return nil end

  -- 1) пробуем прямо в main (на всякий)
  local b = first_build_in(main)
  if b then return b end

  -- 2) пробуем в текущем режиме
  b = first_build_in(main.mode)
  if b then return b end

  -- 3) пробуем в известных режимах
  if type(main.modes) == "table" then
    for _, modeObj in pairs(main.modes) do
      b = first_build_in(modeObj)
      if b then return b end
    end
  end

  return nil
end



function Routes.handle(method, path)
    if method == "GET" and path == "/health" then
    return 200, [[{"ok":true,"service":"pob1-ai-api","game":"poe1","apiVersion":1}]]
  end

    if method == "GET" and path == "/debug/main" then
    local main = _G.PoBAI and _G.PoBAI.pobMain
    if not main then return 200, [[{"ok":false,"error":"no_main"}]] end
    local keys = {}
    for k,_ in pairs(main) do keys[#keys+1] = tostring(k) end
    return 200, '{"ok":true,"mainKeys":"'..table.concat(keys, ",")..'"}'
  end

  if method == "GET" and path == "/debug/mode" then
    local main = _G.PoBAI and _G.PoBAI.pobMain
    local mode = main and main.mode
    if not mode then return 200, [[{"ok":false,"error":"no_mode"}]] end

    return 200, "{"..
      '"ok":true,'..
      '"has_build":'..tostring(mode.build ~= nil)..","..
      '"has_activeBuild":'..tostring(mode.activeBuild ~= nil)..","..
      '"has_builds":'..tostring(mode.builds ~= nil)..
    "}"
  end

  if method == "GET" and path == "/debug/modes" then
    local main = _G.PoBAI and _G.PoBAI.pobMain
    local modes = main and main.modes
    if type(modes) ~= "table" then return 200, [[{"ok":false,"error":"no_modes"}]] end

    local parts = {}
    for k, m in pairs(modes) do
      local hasBuild = (type(m)=="table" and m.build ~= nil) and "true" or "false"
      local hasBuilds = (type(m)=="table" and m.builds ~= nil) and "true" or "false"
      parts[#parts+1] = '"'..tostring(k)..'":{"has_build":'..hasBuild..',"has_builds":'..hasBuilds..'}'
    end
    return 200, "{"..'"ok":true,"modes":{'..table.concat(parts, ",").."}}"
  end


  if method == "GET" and path == "/state" then
    local build = get_active_build()
    if not build then
      return 200, json_obj({ ok=false, error="no_active_build" })
    end
    -- минимально: имя класса/уровень, если доступно
    local out = build.output or {}
    return 200, json_obj({
      ok=true,
      level = build.characterLevel or out.Level or 1,
      class = build.spec and build.spec.curClassName or (out.ClassName or "unknown"),
      ascendancy = build.spec and build.spec.curAscendName or (out.AscendClassName or "none"),
    })
  end

  if method == "GET" and path == "/evaluate" then
    local build = get_active_build()
    if not build then
      return 200, json_obj({ ok=false, error="no_active_build" })
    end

    -- заставим PoB пересчитать output, если есть recalc
    if build.BuildConfig and build.BuildConfig.Build then
      -- пропускаем, на следующем шаге сделаем нормальный recalc вызов
    end

    local out = build.output or {}
    -- Эти поля могут отличаться, поэтому MVP: берём то, что чаще всего есть
    local res = out.ResistFire or out.FireResist or out.FireRes or nil
    local resC = out.ResistCold or out.ColdResist or out.ColdRes or nil
    local resL = out.ResistLightning or out.LightningResist or out.LightningRes or nil
    local resCh = out.ResistChaos or out.ChaosResist or out.ChaosRes or nil

    local life = out.Life or out.TotalLife or nil
    local es = out.EnergyShield or out.TotalEnergyShield or out.ES or nil
    local armour = out.Armour or nil
    local evasion = out.Evasion or nil

    return 200, "{"..
      '"ok":true,'..
      '"defense":{'..
        table.concat({
          json_kv("life", life),
          json_kv("es", es),
          json_kv("armour", armour),
          json_kv("evasion", evasion)
        }, ",")..
      "},"..
      '"resists":{'..
        table.concat({
          json_kv("fire", res),
          json_kv("cold", resC),
          json_kv("lightning", resL),
          json_kv("chaos", resCh)
        }, ",")..
      "}"..
    "}"
  end

  return 404, json_obj({ error="not_found" })
end

return Routes
