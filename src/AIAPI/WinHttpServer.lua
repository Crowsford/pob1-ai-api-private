local ffi = require("ffi")

ffi.cdef[[
typedef unsigned short u_short;
typedef unsigned long  u_long;
typedef unsigned int   uint32_t;
typedef int            SOCKET;
typedef unsigned long  DWORD;
typedef unsigned short WORD;

typedef struct WSAData {
  WORD wVersion;
  WORD wHighVersion;
  char szDescription[257];
  char szSystemStatus[129];
  unsigned short iMaxSockets;
  unsigned short iMaxUdpDg;
  char* lpVendorInfo;
} WSADATA;

typedef struct in_addr { uint32_t S_addr; } IN_ADDR;

typedef struct sockaddr_in {
  short sin_family;
  u_short sin_port;
  IN_ADDR sin_addr;
  char sin_zero[8];
} SOCKADDR_IN;

int WSAStartup(WORD wVersionRequested, WSADATA *lpWSAData);
int WSAGetLastError(void);

SOCKET socket(int af, int type, int protocol);
int bind(SOCKET s, const void* name, int namelen);
int listen(SOCKET s, int backlog);
SOCKET accept(SOCKET s, void* addr, int* addrlen);

int ioctlsocket(SOCKET s, long cmd, u_long *argp);

int recv(SOCKET s, char* buf, int len, int flags);
int send(SOCKET s, const char* buf, int len, int flags);
int closesocket(SOCKET s);

u_short htons(u_short hostshort);
uint32_t inet_addr(const char* cp);
]]

local ws2 = ffi.load("Ws2_32")
local Routes = require("AIAPI.Routes")

local AF_INET      = 2
local SOCK_STREAM  = 1
local IPPROTO_TCP  = 6
local INVALID_SOCKET = ffi.cast("SOCKET", -1)
local SOCKET_ERROR = -1
local FIONBIO      = 0x8004667E
local WSAEWOULDBLOCK = 10035
local MSG_PEEK = 0x2

local function wsa_err() return ws2.WSAGetLastError() end

local function set_nonblocking(sock)
  local arg = ffi.new("u_long[1]", 1)
  ws2.ioctlsocket(sock, FIONBIO, arg)
end

local function respond_and_close(client, statusLine, jsonBody)
  local body = jsonBody or "{}"
  local resp =
    "HTTP/1.1 " .. statusLine .. "\r\n" ..
    "Content-Type: application/json\r\n" ..
    "Connection: close\r\n" ..
    "Content-Length: " .. tostring(#body) .. "\r\n\r\n" ..
    body
  ws2.send(client, resp, #resp, 0)
  ws2.closesocket(client)
end

local Server = {}
Server.__index = Server

function Server:new(opts)
  opts = opts or {}
  return setmetatable({
    host = opts.host or "127.0.0.1",
    port = opts.port or 8080,
    started = false,
    listenSock = nil,
  }, self)
end

function Server:start()
  if self.started then return true end

  local wsa = ffi.new("WSADATA[1]")
  local rc = ws2.WSAStartup(0x0202, wsa)
  if rc ~= 0 then
    return false, "WSAStartup rc=" .. tostring(rc)
  end

  local s = ws2.socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)
  if s == INVALID_SOCKET then
    return false, "socket err=" .. tostring(wsa_err())
  end

  local addr = ffi.new("SOCKADDR_IN[1]")
  addr[0].sin_family = AF_INET
  addr[0].sin_port = ws2.htons(self.port)
  addr[0].sin_addr.S_addr = ws2.inet_addr(self.host)

  if ws2.bind(s, addr, ffi.sizeof(addr[0])) == SOCKET_ERROR then
    local err = wsa_err()
    ws2.closesocket(s)
    return false, "bind err=" .. tostring(err)
  end

  if ws2.listen(s, 16) == SOCKET_ERROR then
    local err = wsa_err()
    ws2.closesocket(s)
    return false, "listen err=" .. tostring(err)
  end

  set_nonblocking(s)
  self.listenSock = s
  self.started = true
  return true
end

function Server:poll()
  if not self.started then return end

  -- ограничим число обработанных клиентов за тик
  for _ = 1, 1 do
    local client = ws2.accept(self.listenSock, nil, nil)
    if client == INVALID_SOCKET then
      local err = wsa_err()
      if err ~= WSAEWOULDBLOCK then
        -- можно логировать, но не спамим
      end
      return
    end

    local ok, err = pcall(function()
      set_nonblocking(client)

      local buf = ffi.new("char[4096]")
      
      -- Peek first to ensure data is ready; avoids weird stalls
      local pn = ws2.recv(client, buf, 4095, MSG_PEEK)
      if pn <= 0 then
        respond_and_close(client, "408 Request Timeout", [[{"error":"no_data"}]])
        return
      end

      local n = ws2.recv(client, buf, 4095, 0)
      if n <= 0 then
        -- нет данных — закрываем
        ws2.closesocket(client)
        return
      end

      local req = ffi.string(buf, n)
      local method, path = req:match("^(%S+)%s+(%S+)")
      if not method or not path then
        respond_and_close(client, "400 Bad Request", [[{"error":"bad_request"}]])
        return
      end

      local status, body = Routes.handle(method, path)
      local statusLine =
        (status == 200 and "200 OK") or
        (status == 404 and "404 Not Found") or
        "500 Internal Server Error"

      respond_and_close(client, statusLine, body)
    end)

    if not ok then
      -- если что-то упало внутри обработчика — постараемся ответить и закрыть
      pcall(function()
        respond_and_close(client, "500 Internal Server Error",
          '{"error":"handler_crash","message":"'..tostring(err):gsub('"','\\"')..'"}')
      end)
      pcall(function() ws2.closesocket(client) end)
    end
  end
end

return Server
