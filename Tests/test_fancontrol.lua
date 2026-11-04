assert(_VERSION == "Lua 5.1", "fancontrol contracts require the deployed Lua 5.1 runtime")
local root = assert(arg[1], "repository root argument is required")
package.path = root .. "/Tests/?.lua;" .. root ..
    "/packages/luci-app-sbe1v1k-fan/root/usr/lib/lua/?.lua;" .. package.path
local fixture = require("fan_fixture")
local core = require("sbe1v1k_fan.core")
local check = require("fan_assertions")
local tests = {}
local equal, sequence = check.equal, check.sequence

function tests.native_status_uses_dt_state_order()
    local state = fixture.new()
    local status = core.new(state.deps):status()
    equal(status.ok, true)
    equal(status.custom, false)
    sequence(status.active, {40, 50, 65, 80}, "active")
    sequence(status.defaults, {40, 50, 65, 80}, "native defaults")
    sequence(status.pwm_levels, {36, 72, 128, 255}, "native PWM levels")
    sequence(status.hysteresis, {1, 1, 1, 1}, "hysteresis")
    equal(status.temperature, 53.75)
    equal(status.pwm, 72)
    equal(status.cooling_state, 1)
    equal(status.policy, "step_wise")
    equal(#status.protections, 3)
    equal(status.protections[1].temperature, 125)
    equal(status.protections[2].temperature, 110)
    equal(status.protections[3].temperature, 100)
    equal(#state.writes, 0, "status must be read-only")
    equal(#state.saves, 0, "status must not persist UCI")
end

function tests.dynamic_thermal_cooling_and_hwmon_indices()
    local state = fixture.new({zone=27, cooling=19, hwmon=34})
    local status = core.new(state.deps):configure(check.thresholds(true))
    equal(status.ok, true)
    equal(status.pwm, 72)
    sequence(status.active, {42, 54, 67, 88}, "dynamic hardware")
    check.only_active_writes(state)
    check.active_files(state, {42, 54, 67, 88})
end

function tests.custom_configuration_writes_exactly_four_active_trips()
    local state = fixture.new()
    local status = core.new(state.deps):configure(check.thresholds(true))
    equal(status.ok, true)
    equal(status.custom, true)
    sequence(status.configured, {42, 54, 67, 88}, "saved configuration")
    sequence(status.active, {42, 54, 67, 88}, "configured active trips")
    sequence(status.defaults, {40, 50, 65, 80}, "immutable native defaults")
    equal(#state.writes, 4, "exactly four active writes")
    equal(#state.saves, 1, "one successful UCI commit")
    equal(state.get_config().t3, 88)
    assert(state.lock_count > 0, "hardware transaction must hold a lock")
    check.only_active_writes(state)
    check.active_files(state, {42, 54, 67, 88})
end

function tests.native_mode_restores_dt_defaults_and_preserves_saved_custom_values()
    local state = fixture.new()
    local service = core.new(state.deps)
    service:configure(check.thresholds(true))
    local status = service:configure(check.thresholds(false))
    equal(status.custom, false)
    sequence(status.configured, {42, 54, 67, 88}, "retained custom configuration")
    sequence(status.active, {40, 50, 65, 80}, "restored native values")
    check.only_active_writes(state)
    check.active_files(state, {40, 50, 65, 80})
end

function tests.native_restore_uses_device_tree_values_instead_of_constants()
    local trips, defaults = {}, {41000, 52000, 66000, 82000}
    for index, original in ipairs(fixture.native_trips) do
        local trip = {}
        for key, value in pairs(original) do trip[key] = value end
        if trip.state then trip.temp = defaults[trip.state + 1] end
        trips[index] = trip
    end
    local state = fixture.new({trips=trips})
    local service = core.new(state.deps)
    service:configure(check.thresholds(true))
    local status = service:configure(check.thresholds(false))
    sequence(status.defaults, {41, 52, 66, 82}, "defaults from current DTB")
    sequence(status.active, {41, 52, 66, 82}, "restored current DTB values")
end

function tests.boot_apply_uses_saved_mode_without_a_new_uci_commit()
    local state = fixture.new()
    state.set_config(check.thresholds(true))
    local status = core.new(state.deps):apply()
    sequence(status.active, {42, 54, 67, 88}, "boot applies custom values")
    equal(#state.saves, 0, "boot does not rewrite UCI")
    check.only_active_writes(state)
end

function tests.native_apply_restores_active_trip_drift()
    local state = fixture.new()
    state.files[state.zone .. "/trip_point_6_temp"] = "45000\n"
    local status = core.new(state.deps):apply()
    sequence(status.active, {40, 50, 65, 80}, "native apply")
    equal(#state.saves, 0)
    check.only_active_writes(state)
end

function tests.dt_order_can_change_without_changing_state_order()
    local native = fixture.native_trips
    local state = fixture.new({trips={native[7], native[1], native[5], native[2],
        native[4], native[3], native[6]}})
    local status = core.new(state.deps):configure(check.thresholds(true))
    sequence(status.active, {42, 54, 67, 88}, "state order survives DT index changes")
    equal(tonumber(state.files[state.zone .. "/trip_point_0_temp"]), 42000)
    equal(tonumber(state.files[state.zone .. "/trip_point_6_temp"]), 54000)
    equal(tonumber(state.files[state.zone .. "/trip_point_2_temp"]), 67000)
    equal(tonumber(state.files[state.zone .. "/trip_point_4_temp"]), 88000)
    equal(tonumber(state.files[state.zone .. "/trip_point_1_temp"]), 125000)
end

for name, callback in pairs(require("fan_validation")) do tests[name] = callback end
for name, callback in pairs(require("fan_failures")) do tests[name] = callback end

local names = {}
for name in pairs(tests) do names[#names + 1] = name end
table.sort(names)
local failures = 0
for _, name in ipairs(names) do
    local ok, failure = pcall(tests[name])
    if ok then
        io.write("PASS " .. name .. "\n")
    else
        failures = failures + 1
        io.write("FAIL " .. name .. ": " .. tostring(failure) .. "\n")
    end
end
assert(failures == 0, tostring(failures) .. " fancontrol tests failed")
io.write(tostring(#names) .. " fancontrol scenarios passed\n")
