local fixture = require("fan_fixture")
local core = require("sbe1v1k_fan.core")
local check = require("fan_assertions")
local tests = {}

local function invalid(value)
    local state = fixture.new()
    check.rejected(function() core.new(state.deps):configure(value) end)
    check.equal(#state.writes, 0, "invalid input must not reach hardware writes")
    check.equal(#state.saves, 0, "invalid input must not persist")
end

function tests.payload_requires_boolean_mode_and_all_four_temperatures()
    invalid(nil)
    invalid(false)
    invalid("invalid")
    invalid(1)
    invalid({})
    invalid({custom=true})
    invalid({custom="true", t0=40, t1=50, t2=65, t3=80})
    invalid({custom=1, t0=40, t1=50, t2=65, t3=80})
    invalid({custom=false, t0=40, t1=50, t2=65})
end

function tests.thresholds_reject_non_numeric_non_finite_or_fractional_values()
    for _, value in ipairs({"40", "", true, 40.5, math.huge, -math.huge, 0/0}) do
        local payload = check.thresholds(true)
        payload.t0 = value
        invalid(payload)
    end
end

function tests.thresholds_must_be_strictly_increasing()
    invalid({custom=true, t0=50, t1=50, t2=65, t3=80})
    invalid({custom=true, t0=60, t1=50, t2=65, t3=80})
    invalid({custom=true, t0=40, t1=65, t2=65, t3=80})
    invalid({custom=true, t0=40, t1=50, t2=80, t3=80})
    invalid({custom=true, t0=40, t1=50, t2=90, t3=80})
end

function tests.highest_threshold_must_stay_below_hot_and_critical_trips()
    invalid({custom=true, t0=40, t1=50, t2=65, t3=100})
    invalid({custom=true, t0=40, t1=50, t2=65, t3=125})
    local state = fixture.new()
    state.files[state.zone .. "/trip_point_2_temp"] = "85000\n"
    check.rejected(function() core.new(state.deps):configure(check.thresholds(true)) end)
    check.equal(#state.writes, 0, "actual protection threshold constrains writes")
end

function tests.valid_integer_thresholds_have_no_invented_temperature_floor()
    local state = fixture.new()
    local payload = {custom=true, t0=-5, t1=0, t2=20, t3=99}
    local status = core.new(state.deps):configure(payload)
    check.sequence(status.active, {-5, 0, 20, 99}, "valid full range")
    check.only_active_writes(state)
end

function tests.configuration_rejects_disabled_thermal_zone_without_enabling_it()
    local state = fixture.new()
    state.files[state.zone .. "/mode"] = "disabled\n"
    core.new(state.deps):status()
    check.rejected(function() core.new(state.deps):configure(check.thresholds(true)) end)
    check.equal(#state.writes, 0)
    check.equal(state.files[state.zone .. "/mode"], "disabled\n")
end

function tests.configuration_rejects_another_policy_without_replacing_it()
    local state = fixture.new()
    state.files[state.zone .. "/policy"] = "user_space\n"
    check.equal(core.new(state.deps):status().policy, "user_space")
    check.rejected(function() core.new(state.deps):configure(check.thresholds(true)) end)
    check.equal(#state.writes, 0)
    check.equal(state.files[state.zone .. "/policy"], "user_space\n")
end

function tests.boot_rejects_invalid_saved_custom_configuration()
    local state = fixture.new()
    state.set_config({custom=true, t0=50, t1=40, t2=65, t3=80})
    check.rejected(function() core.new(state.deps):apply() end)
    check.equal(#state.writes, 0)
end

return tests
