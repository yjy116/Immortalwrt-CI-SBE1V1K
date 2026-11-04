local nixio = require "nixio"
local fs = require "nixio.fs"
local uci = require "uci"
local M = {}
local PACKAGE, SECTION = "sbe1v1k-fan", "settings"
local LOCK, LOCK_MODE = "/var/lock/sbe1v1k-fan.lock", "rw-------"
local STATES = 4

local function read_file(path)
    local value, code, message = fs.readfile(path)
    return value, message or code
end

local function write_file(path, value)
    local file, code, message = nixio.open(path, "w")
    if not file then return nil, message or code end
    local wrote, write_code, write_message = file:writeall(value)
    local closed, close_code, close_message = file:close()
    if not wrote then return nil, write_message or write_code end
    if not closed then return nil, close_message or close_code end
    return true
end

local function list_directory(path)
    local iterator, code, message = fs.dir(path)
    if not iterator then return nil, message or code end
    local entries = {}
    for name in iterator do entries[#entries + 1] = name end
    table.sort(entries)
    return entries
end

local function realpath(path)
    local value, code, message = fs.realpath(path)
    return value, message or code
end

local function load_config()
    local cursor = uci.cursor()
    local loaded, problem = cursor:load(PACKAGE)
    assert(loaded, "Cannot load fan UCI configuration: " .. tostring(problem))
    assert(cursor:get(PACKAGE, SECTION) == "fan", "Missing fan UCI settings section")
    return cursor
end

local function read_config()
    local cursor = load_config()
    local custom = cursor:get(PACKAGE, SECTION, "custom")
    assert(custom == "0" or custom == "1", "Invalid UCI custom mode")
    local result = {custom=custom == "1"}
    for state = 0, STATES - 1 do
        local key = "t" .. state
        result[key] = tonumber(cursor:get(PACKAGE, SECTION, key))
    end
    cursor:unload(PACKAGE)
    return result
end

local function save_config(config)
    local cursor = load_config()
    assert(cursor:set(PACKAGE, SECTION, "custom", config.custom and "1" or "0"), "Cannot set custom mode")
    for state = 0, STATES - 1 do
        local key = "t" .. state
        assert(cursor:set(PACKAGE, SECTION, key, tostring(config[key])), "Cannot set UCI " .. key)
    end
    local committed, problem = cursor:commit(PACKAGE)
    cursor:unload(PACKAGE)
    return committed, problem
end

local function with_lock(callback)
    local file, code, message = nixio.open(LOCK, "w", LOCK_MODE)
    assert(file, "Cannot open fan lock: " .. tostring(message or code))
    local locked, lock_code, lock_message = file:lock("tlock")
    if not locked then
        file:close()
        error("Another fan operation holds the lock: " .. tostring(lock_message or lock_code))
    end
    local ok, result = pcall(callback)
    local closed, close_code, close_message = file:close()
    if not ok then error(result) end
    assert(closed, "Cannot close fan lock: " .. tostring(close_message or close_code))
    return result
end

function M.dependencies()
    return {fs={read=read_file, write=write_file, list=list_directory, realpath=realpath},
        config={read=read_config, save=save_config}, with_lock=with_lock}
end

return M
