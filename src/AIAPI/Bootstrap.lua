local function log(msg)
  local f = io.open("pob-ai.log", "a")
  if f then
    f:write(os.date("%Y-%m-%d %H:%M:%S ") .. msg .. "\n")
    f:close()
  end
end

_G.PoBAI = _G.PoBAI or {}
local ENABLE_HTTP = false

-- монотонные миллисекунды (не зависит от GetTime)
local function now_ms()
  if type(GetTime) == "function" then
    local ok, v = pcall(GetTime)
    if ok and type(v) == "number" then return v end
  end
  return math.floor((os.clock() or 0) * 1000)
end

local function norm_path(p)
  p = tostring(p or ""):gsub("/", "\\")
  if p ~= "" and p:sub(-1) == "\\" then p = p:sub(1, -2) end
  return p
end

local function ensure_package_path(root)
  if not root or root == "" then return end
  root = norm_path(root)

  -- добавим root\?.lua и root\?\init.lua
  local p1 = root .. "\\?.lua"
  local p2 = root .. "\\?\\init.lua"
  if not package.path:find(p1, 1, true) then
    package.path = p1 .. ";" .. package.path
  end
  if not package.path:find(p2, 1, true) then
    package.path = p2 .. ";" .. package.path
  end
end

function _G.PoBAI.init()
  if _G.PoBAI.inited then return end
  _G.PoBAI.inited = true
  _G.PoBAI.tickCount = 0

  log("PoBAI: init OK")

  local okFfi = pcall(require, "ffi")
  log("PoBAI: require('ffi') = " .. tostring(okFfi))

  local okSock = pcall(require, "socket")
  log("PoBAI: require('socket') = " .. tostring(okSock))

  -- ROOT из окружения (ты его ставишь setx /M)
  local envRoot = norm_path(os.getenv("POB_AI_IPC_ROOT"))
  log("PoBAI: env POB_AI_IPC_ROOT=" .. tostring(envRoot))

  ensure_package_path(envRoot)
  log("PoBAI: package.path=" .. tostring(package.path))

  if ENABLE_HTTP then
    local okSrv, Server = pcall(require, "AIAPI.WinHttpServer")
    log("PoBAI: require('AIAPI.WinHttpServer') = " .. tostring(okSrv))
    if okSrv and Server then
      _G.PoBAI.http = _G.PoBAI.http or Server:new({ host = "127.0.0.1", port = 18080 })
      local okStart, err = _G.PoBAI.http:start()
      log("PoBAI: http start=" .. tostring(okStart) .. (err and (" err="..tostring(err)) or ""))
    end
  end

  package.loaded["AIAPI.FileIPC"] = nil
local okIpc, IPC_or_err = pcall(require, "AIAPI.FileIPC")
log("PoBAI: require('AIAPI.FileIPC') = " .. tostring(okIpc))
if not okIpc then
  log("PoBAI: require('AIAPI.FileIPC') err=" .. tostring(IPC_or_err))
  _G.PoBAI.ipc = nil
else
  _G.PoBAI.ipc = IPC_or_err
end

end

function _G.PoBAI.tick()
  if not _G.PoBAI.inited then return end
  _G.PoBAI.tickCount = (_G.PoBAI.tickCount or 0) + 1

  local now = now_ms()

  -- IPC poll 5 раз/сек
  _G.PoBAI.nextIpc = _G.PoBAI.nextIpc or 0
  if now >= _G.PoBAI.nextIpc then
    _G.PoBAI.nextIpc = now + 200
    if _G.PoBAI.ipc and _G.PoBAI.ipc.poll_once then
      local ok, err = pcall(function() _G.PoBAI.ipc:poll_once() end)
      if not ok then log("PoBAI: ipc poll_once err=" .. tostring(err)) end
    end
  end

  if _G.PoBAI.tickCount % 600 == 0 then
    log("PoBAI: tick " .. tostring(_G.PoBAI.tickCount))
  end
end