local fdt = require "sbe1v1k_fan.fdt"
local M = {}
local STATES, PWM_MAX = 4, 255
local ZONE = "top-glue-thermal"

local function cell(node, name)
    local values = fdt.cells(node.properties[name])
    assert(#values == 1, "Expected one cell: " .. name)
    return values[1]
end

local function compatible(node, expected)
    local value = node.properties.compatible
    assert(type(value) == "string", "Missing device compatibility")
    for entry in value:gmatch("([^%z]+)%z") do
        if entry == expected then return true end
    end
    return false
end

local function collect_trips(node)
    local result, handles = {}, {}
    for index, child in ipairs(node.children) do
        local trip = {index=index - 1, name=child.name,
            type=fdt.string(child.properties.type),
            default=cell(child, "temperature"), hysteresis=cell(child, "hysteresis")}
        result[index] = trip
        if child.properties.phandle then
            local handle = cell(child, "phandle")
            assert(not handles[handle], "Duplicate trip phandle")
            handles[handle] = trip
        end
    end
    return result, handles
end

local function mapped_trip(node, context)
    local target = fdt.cells(node.properties["cooling-device"])
    assert(#target == 3 and target[1] == context.fan_handle,
        "Unexpected cooling device in SBE fan zone")
    local state = target[2]
    assert(state == target[3] and state >= 0 and state < STATES,
        "Unsupported SBE fan cooling-state bounds")
    local trip = context.handles[cell(node, "trip")]
    assert(trip and trip.type == "active", "Fan map must refer to an active trip")
    assert(not context.active[state + 1], "Duplicate fan cooling state")
    context.active[state + 1] = {index=trip.index, name=trip.name,
        default=trip.default, hysteresis=trip.hysteresis, type=trip.type, state=state}
end

local function validate_active(trips, active)
    local active_count = 0
    for _, trip in ipairs(trips) do
        if trip.type == "active" then active_count = active_count + 1 end
    end
    assert(active_count == STATES, "Expected four native active fan trips")
    local used = {}
    for state = 1, STATES do
        local trip = active[state]
        assert(trip and not used[trip.index], "Missing or duplicate active fan trip")
        used[trip.index] = true
    end
end

function M.profile(bytes)
    local root = fdt.parse(bytes)
    assert(compatible(root, "askey,sbe1v1k"), "This plugin requires Askey SBE1V1K")
    local fan = fdt.child(root, "pwm-fan")
    assert(compatible(fan, "pwm-fan"), "Unsupported fan driver")
    local levels = fdt.cells(fan.properties["cooling-levels"])
    assert(#levels == STATES, "Expected four PWM cooling levels")
    for _, level in ipairs(levels) do assert(level <= PWM_MAX, "Invalid PWM level") end
    local zone = fdt.child(fdt.child(root, "thermal-zones"), ZONE)
    local trips, handles = collect_trips(fdt.child(zone, "trips"))
    local context = {fan_handle=cell(fan, "phandle"), handles=handles, active={}}
    for _, map in ipairs(fdt.child(zone, "cooling-maps").children) do
        mapped_trip(map, context)
    end
    validate_active(trips, context.active)
    return {zone_type=ZONE, trips=trips, active=context.active, levels=levels}
end

return M
