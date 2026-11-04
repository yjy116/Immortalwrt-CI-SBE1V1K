#!/usr/bin/lua
local json = require "luci.jsonc"
local methods = {status={}, configure={custom=false, t0=0, t1=0, t2=0, t3=0}}

local function invoke(command, method)
    local core = require "sbe1v1k_fan.core"
    local platform = require "sbe1v1k_fan.platform"
    local service = core.new(platform.dependencies())
    if command == "apply" then return service:apply() end
    assert(command == "call" and methods[method], "Unknown fan RPC method")
    if method == "status" then return service:status() end
    local payload, problem = json.parse(io.read("*a"))
    assert(type(payload) == "table", "Invalid configure JSON: " .. tostring(problem))
    return service:configure(payload)
end

if arg[1] == "list" then
    -- lua-jsonc encodes an empty Lua table as []; rpcd requires an object here.
    io.write('{"status":{},"configure":{"custom":false,"t0":0,"t1":0,"t2":0,"t3":0}}\n')
else
    local ok, result = pcall(invoke, arg[1], arg[2])
    if not ok then result = {ok=false, error=tostring(result)} end
    io.write(json.stringify(result), "\n")
    if not ok and arg[1] == "apply" then os.exit(1) end
end
