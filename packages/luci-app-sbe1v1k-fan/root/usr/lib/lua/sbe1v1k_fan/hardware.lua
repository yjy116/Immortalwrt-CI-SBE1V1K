local device_tree = require "sbe1v1k_fan.device_tree"
local M = {}
local THERMAL, HWMON = "/sys/class/thermal", "/sys/class/hwmon"
local MILLI, STATES, PWM_MAX = 1000, 4, 255

function M.read(fs, path)
    local value, problem = fs.read(path)
    assert(type(value) == "string", "Cannot read " .. path .. ": " .. tostring(problem))
    return value
end

function M.text(fs, path)
    return (M.read(fs, path):gsub("%s+$", ""))
end

function M.number(fs, path)
    local value = M.text(fs, path)
    assert(value:match("^%-?%d+$"), "Invalid sysfs integer: " .. path)
    return tonumber(value)
end

local function listing(fs, path)
    local values, problem = fs.list(path)
    assert(type(values) == "table", "Cannot list " .. path .. ": " .. tostring(problem))
    return values
end

local function find_device(fs, request)
    local found
    for _, name in ipairs(listing(fs, request.root)) do
        if name:match(request.pattern) then
            local path = request.root .. "/" .. name
            if M.text(fs, path .. "/" .. request.attribute) == request.value then
                assert(not found, "Multiple matching devices: " .. request.value)
                found = path
            end
        end
    end
    assert(found, "Missing hardware: " .. request.value)
    return found
end

local function canonical(fs, path)
    local target, problem = fs.realpath(path)
    assert(type(target) == "string", "Cannot resolve " .. path .. ": " .. tostring(problem))
    return target
end

local function bindings(fs, context)
    local result = {}
    local fan = canonical(fs, context.cooling)
    for _, name in ipairs(listing(fs, context.zone)) do
        if name:match("^cdev%d+$") and canonical(fs, context.zone .. "/" .. name) == fan then
            local trip = M.number(fs, context.zone .. "/" .. name .. "_trip_point")
            assert(not result[trip], "Duplicate runtime fan trip binding")
            result[trip] = true
        end
    end
    return result
end

local function trips_snapshot(fs, context)
    local protections, actual, hysteresis, paths = {}, {}, {}, {}
    local linked = bindings(fs, context)
    for _, trip in ipairs(context.profile.trips) do
        local path = context.zone .. "/trip_point_" .. trip.index
        assert(M.text(fs, path .. "_type") == trip.type, "Runtime and DT trip types differ")
        if trip.type == "hot" or trip.type == "critical" then
            protections[#protections + 1] = {type=trip.type,
                temperature=M.number(fs, path .. "_temp") / MILLI}
        end
    end
    for state, trip in ipairs(context.profile.active) do
        assert(linked[trip.index], "Missing runtime fan cooling-map binding")
        linked[trip.index] = nil
        paths[state] = context.zone .. "/trip_point_" .. trip.index .. "_temp"
        actual[state] = M.number(fs, paths[state]) / MILLI
        hysteresis[state] = M.number(fs, context.zone .. "/trip_point_" .. trip.index .. "_hyst") / MILLI
    end
    assert(next(linked) == nil, "Unexpected runtime fan trip binding")
    assert(#protections > 0, "Missing native thermal protection trips")
    return {active=actual, hysteresis=hysteresis, protections=protections, paths=paths}
end

local function devices(fs, profile)
    local zone = find_device(fs, {root=THERMAL, pattern="^thermal_zone%d+$",
        attribute="type", value=profile.zone_type})
    local cooling = find_device(fs, {root=THERMAL, pattern="^cooling_device%d+$",
        attribute="type", value="pwm-fan"})
    local hwmon = find_device(fs, {root=HWMON, pattern="^hwmon%d+$",
        attribute="name", value="pwmfan"})
    assert(M.number(fs, cooling .. "/max_state") == STATES - 1, "Unexpected fan state count")
    return {zone=zone, cooling=cooling, hwmon=hwmon, profile=profile}
end

function M.snapshot(fs)
    local profile = device_tree.profile(M.read(fs, "/sys/firmware/fdt"))
    local context = devices(fs, profile)
    local result = trips_snapshot(fs, context)
    result.defaults = {}
    for state, trip in ipairs(profile.active) do result.defaults[state] = trip.default / MILLI end
    result.pwm_levels = profile.levels
    result.temperature = M.number(fs, context.zone .. "/temp") / MILLI
    result.pwm = M.number(fs, context.hwmon .. "/pwm1")
    result.cooling_state = M.number(fs, context.cooling .. "/cur_state")
    result.policy = M.text(fs, context.zone .. "/policy")
    result.mode = M.text(fs, context.zone .. "/mode")
    assert(result.pwm >= 0 and result.pwm <= PWM_MAX, "Invalid current PWM")
    assert(result.cooling_state >= 0 and result.cooling_state < STATES, "Invalid cooling state")
    return result
end

return M
