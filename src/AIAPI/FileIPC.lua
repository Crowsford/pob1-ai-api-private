local FileIPC = {}

local function log(msg)
  local f = io.open("pob-ai.log", "a")
  if f then
    f:write(os.date("%Y-%m-%d %H:%M:%S ") .. msg .. "\n")
    f:close()
  end
end

local function norm_path(p)
  p = tostring(p or ""):gsub("/", "\\")
  return p
end

local function ensure_trailing_slash(p)
  p = norm_path(p)
  if p ~= "" and p:sub(-1) ~= "\\" then p = p .. "\\" end
  return p
end

-- ASCII->UTF16 (для твоих путей D:\Dev\... хватает; если будут кириллица/юникод — расширим)
local function to_wide(s)
  s = tostring(s or "")
  local n = #s
  local buf = require("ffi").new("wchar_t[?]", n + 1)
  for i = 1, n do
    buf[i - 1] = s:byte(i)
  end
  buf[n] = 0
  return buf
end

local function read_all(path)
  local f = io.open(path, "rb")
  if not f then return nil end
  local s = f:read("*a")
  f:close()
  return s
end

local function write_all(path, s)
  local f = io.open(path, "wb")
  if not f then return false end
  f:write(s)
  f:close()
  return true
end

local function parse_request(txt)
  local req = {}
  for line in tostring(txt):gmatch("[^\r\n]+") do
    local k, v = line:match("^([%w_]+)=(.*)$")
    if k then req[k] = v end
  end
  if not req.id then return nil, "missing id" end
  if not req.cmd then return nil, "missing cmd" end
  return req
end

local function handle(req)
  if req.cmd == "health" then
    return true, [[{"ok":true,"service":"pob1-ai-engine","game":"poe1","apiVersion":1}]]
  end

  if req.cmd == "debug_modes" then
    local main = rawget(_G, "main") or (_G.PoBAI and _G.PoBAI.pobMain)
    if type(main) ~= "table" then
      return true, [[{"ok":false,"error":"no_main"}]]
    end

    local modes = rawget(main, "modes")
    if type(modes) ~= "table" then
      return true, [[{"ok":false,"error":"no_modes"}]]
    end

    local keys = {}
    for k,_ in pairs(modes) do
      keys[#keys+1] = tostring(k)
    end
    table.sort(keys)

    return true, [[{"ok":true,"modes":"]] .. table.concat(keys, ",") .. [["}]]
  end

  if req.cmd == "state" then
    local main = rawget(_G, "main") or (_G.PoBAI and _G.PoBAI.pobMain)
    local build = main and main.modes and main.modes["BUILD"]

    if type(build) ~= "table" then
      return true, [[{"ok":true,"has_build":false}]]
    end

    local className, ascendClassName, level

    local spec = rawget(build, "spec")

    if type(spec) == "table" then
        className = rawget(spec, "curClassName")
        ascendClassName = rawget(spec, "curAscendClassName")
    end

    level = rawget(build, "characterLevel")
    local char = rawget(build, "character")
    if type(char) == "table" then
      className = rawget(char, "className") or rawget(char, "class")
      ascendClassName = rawget(char, "ascendClassName") or rawget(char, "ascendClass")
      level = rawget(char, "level")
    end

    local cfg = rawget(build, "config")
    if not level and type(cfg) == "table" then
      level = rawget(cfg, "level")
    end

    local function jstr(v)
      v = tostring(v or "")
      v = v:gsub("\\", "\\\\"):gsub('"', '\\"')
      return '"'..v..'"'
    end

    local parts = {}
    parts[#parts+1] = [["ok":true]]
    parts[#parts+1] = [["has_build":true]]
    if className then parts[#parts+1] = [["className":]]..jstr(className) end
    if ascendClassName then parts[#parts+1] = [["ascendClassName":]]..jstr(ascendClassName) end
    if level then parts[#parts+1] = [["level":]]..tostring(tonumber(level) or 0) end
    -- Read-only calculated stats from Path of Building
    local calcsTab = rawget(build, "calcsTab")
    local output = type(calcsTab) == "table" and rawget(calcsTab, "mainOutput")

    if type(output) == "table" then
      local statKeys = {
        Life = "life",
        LifeUnreserved = "lifeUnreserved",
        Mana = "mana",
        ManaUnreserved = "manaUnreserved",
        FullDPS = "fullDPS",
        TotalDPS = "totalDPS",
        TotalEHP = "totalEHP",
      }

      local stats = {}

      for sourceKey, jsonKey in pairs(statKeys) do
        local value = tonumber(rawget(output, sourceKey))
        if value and value == value and value ~= math.huge and value ~= -math.huge then
          stats[#stats+1] = jstr(jsonKey) .. ":" .. tostring(value)
        end
      end

      parts[#parts+1] = [["stats":{]] .. table.concat(stats, ",") .. "}"
    end

    return true, "{"..table.concat(parts, ",").."}"
  end

	if req.cmd == "debug_main_keys" then
  local main = rawget(_G, "main") or (_G.PoBAI and _G.PoBAI.pobMain)
  if type(main) ~= "table" then
    return true, [[{"ok":false,"error":"no_main"}]]
  end

  local keys = {}
  for k,_ in pairs(main) do
    keys[#keys+1] = tostring(k)
  end
  table.sort(keys)

  return true, [[{"ok":true,"main_keys":"]] .. table.concat(keys, ",") .. [["}]]
end

  return false, [[{"ok":false,"error":"unknown_cmd"}]]
end


-- ---- WinAPI FindFirstFileW / FindNextFileW ----
local ffi_ok, ffi = pcall(require, "ffi")
if not ffi_ok or not ffi then
  log("FileIPC: FFI not available")
  return FileIPC
end

-- guard, чтобы cdef НЕ повторялся (иначе ловишь "attempt to redefine ...")
if not _G.__POBAI_WINAPI_CDEF_DONE then
  _G.__POBAI_WINAPI_CDEF_DONE = true
  ffi.cdef[[
    typedef void* HANDLE;
    typedef unsigned long DWORD;
    typedef unsigned short WCHAR;
    typedef WCHAR* LPWSTR;
    typedef const WCHAR* LPCWSTR;
    typedef int BOOL;

    typedef struct _FILETIME {
      DWORD dwLowDateTime;
      DWORD dwHighDateTime;
    } FILETIME;

    typedef struct _WIN32_FIND_DATAW {
      DWORD    dwFileAttributes;
      FILETIME ftCreationTime;
      FILETIME ftLastAccessTime;
      FILETIME ftLastWriteTime;
      DWORD    nFileSizeHigh;
      DWORD    nFileSizeLow;
      DWORD    dwReserved0;
      DWORD    dwReserved1;
      WCHAR    cFileName[260];
      WCHAR    cAlternateFileName[14];
    } WIN32_FIND_DATAW;

    HANDLE FindFirstFileW(LPCWSTR lpFileName, WIN32_FIND_DATAW* lpFindFileData);
    BOOL   FindNextFileW(HANDLE hFindFile, WIN32_FIND_DATAW* lpFindFileData);
    BOOL   FindClose(HANDLE hFindFile);
    DWORD  GetLastError(void);
  ]]
end

local INVALID_HANDLE_VALUE = ffi.cast("HANDLE", -1)
local FILE_ATTRIBUTE_DIRECTORY = 0x10

local function wchar_to_lua(ws)
  -- ws = WCHAR[260]
  local t = {}
  for i = 0, 259 do
    local c = ws[i]
    if c == 0 then break end
    t[#t+1] = string.char(tonumber(c) % 256)
  end
  return table.concat(t)
end

local function first_req_filename(inbox_dir)
  local pattern = ensure_trailing_slash(inbox_dir) .. "*.req"
  local data = ffi.new("WIN32_FIND_DATAW[1]")
  local h = ffi.C.FindFirstFileW(to_wide(pattern), data)
  if h == INVALID_HANDLE_VALUE then
    local err = tonumber(ffi.C.GetLastError())
    -- 2 = file not found (обычно просто пустая папка)
    if err ~= 2 then
      log("FileIPC: FindFirstFileW failed err=" .. tostring(err) .. " pattern=" .. pattern)
    end
    return nil
  end

  local function is_dir(d)
    return bit32 and bit32.band(d.dwFileAttributes, FILE_ATTRIBUTE_DIRECTORY) ~= 0
           or (d.dwFileAttributes % (FILE_ATTRIBUTE_DIRECTORY*2) >= FILE_ATTRIBUTE_DIRECTORY) -- fallback
  end

  local name = nil
  repeat
    local d = data[0]
    local n = wchar_to_lua(d.cFileName)
    if n ~= "." and n ~= ".." then
      if not is_dir(d) then
        name = n
        break
      end
    end
  until ffi.C.FindNextFileW(h, data) == 0

  ffi.C.FindClose(h)
  return name
end

local function get_ipc_dirs()
  local root = os.getenv("POB_AI_IPC_ROOT")
  root = ensure_trailing_slash(root)
  return root .. "aiipc\\inbox", root .. "aiipc\\outbox", root
end

function FileIPC:poll_once()
  local INBOX, OUTBOX, ROOT = get_ipc_dirs()

  if not FileIPC._loggedPaths then
    log("FileIPC LOADED FROM: @.\\AIAPI\\FileIPC.lua")
    log("FileIPC: IPC_ROOT=" .. tostring(ROOT))
    log("FileIPC: INBOX=" .. tostring(INBOX))
    log("FileIPC: OUTBOX=" .. tostring(OUTBOX))
    FileIPC._loggedPaths = true
  end

  local name = first_req_filename(INBOX)
  if not name then return end

  local inPath = INBOX .. "\\" .. name
  local txt = read_all(inPath)
  if not txt then
    log("FileIPC: read_all failed for " .. tostring(inPath))
    return
  end

  local req, err = parse_request(txt)
  if not req then
    log("FileIPC: bad request " .. tostring(name) .. " err=" .. tostring(err))
    os.remove(inPath)
    return
  end

  local ok, body = handle(req)
  local out = "id="..tostring(req.id).."\nok="..tostring(ok).."\nbody="..tostring(body).."\n"

  local outPath = OUTBOX .. "\\" .. tostring(req.id) .. ".resp"
  local w = write_all(outPath, out)
  if not w then
    log("FileIPC: write_all failed for " .. tostring(outPath))
    return
  end

  os.remove(inPath)
end

return FileIPC
