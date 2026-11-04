local fixture = require("fan_fixture")
local core = require("sbe1v1k_fan.core")
local check = require("fan_assertions")
local tests = {}

local function unavailable(change)
    local state = fixture.new()
    change(state)
    check.rejected(function() core.new(state.deps):configure(check.thresholds(true)) end)
    check.equal(#state.writes, 0, "missing hardware must fail before writing")
    check.equal(#state.saves, 0, "missing hardware must not persist")
end

function tests.missing_thermal_zone_is_not_simulated()
    unavailable(function(state) state.files[state.zone .. "/type"] = "unrelated\n" end)
end

function tests.missing_hwmon_is_not_simulated()
    unavailable(function(state) state.files[state.hwmon .. "/name"] = "unrelated\n" end)
end

function tests.missing_device_tree_is_not_replaced_by_hardcoded_defaults()
    unavailable(function(state) state.files["/sys/firmware/fdt"] = nil end)
end

function tests.truncated_device_tree_fails_explicitly()
    unavailable(function(state) state.files["/sys/firmware/fdt"] = "invalid FDT" end)
end

function tests.another_device_tree_cannot_activate_sbe_fan_control()
    unavailable(function(state)
        state.files["/sys/firmware/fdt"] = state.files["/sys/firmware/fdt"]:gsub(
            "askey,sbe1v1k", "askey,otherxx")
    end)
end

function tests.mismatched_runtime_trip_type_is_rejected()
    unavailable(function(state) state.files[state.zone .. "/trip_point_3_type"] = "critical\n" end)
end

function tests.binding_an_active_state_to_a_protection_trip_is_rejected()
    unavailable(function(state) state.files[state.zone .. "/cdev4_trip_point"] = "0\n" end)
end

function tests.missing_cooling_link_cannot_be_assumed_from_trip_order()
    unavailable(function(state) state.paths[state.zone .. "/cdev4"] = nil end)
end

function tests.unknown_cooling_state_range_is_rejected()
    unavailable(function(state)
        state.files[state.cooling .. "/max_state"] = "4\n"
        state.files[state.paths[state.cooling] .. "/max_state"] = "4\n"
    end)
end

function tests.missing_protection_read_fails_before_any_write()
    unavailable(function(state) state.files[state.zone .. "/trip_point_0_temp"] = nil end)
end

function tests.missing_active_read_fails_before_any_write()
    unavailable(function(state) state.files[state.zone .. "/trip_point_4_temp"] = nil end)
end

function tests.pwm_read_failure_is_visible_without_fallback_values()
    local state = fixture.new()
    state.failures.read = state.hwmon .. "/pwm1"
    check.rejected(function() core.new(state.deps):status() end, "read")
    check.equal(#state.writes, 0)
end

function tests.configuration_read_failure_is_visible()
    local state = fixture.new()
    state.failures.config_read = true
    check.rejected(function() core.new(state.deps):apply() end, "read")
    check.equal(#state.writes, 0)
end

function tests.write_failure_is_reported_and_prior_trip_writes_are_rolled_back()
    local state = fixture.new()
    state.failures.write = state.zone .. "/trip_point_4_temp"
    check.rejected(function() core.new(state.deps):configure(check.thresholds(true)) end, "write")
    check.active_files(state, {40, 50, 65, 80})
    check.only_active_writes(state)
    check.equal(#state.saves, 0, "failed hardware change must not commit UCI")
end

function tests.successful_write_with_wrong_readback_is_not_success()
    local state = fixture.new()
    state.failures.readback = state.zone .. "/trip_point_4_temp"
    check.rejected(function() core.new(state.deps):configure(check.thresholds(true)) end)
    check.active_files(state, {40, 50, 65, 80})
    check.only_active_writes(state)
    check.equal(#state.saves, 0)
end

function tests.readback_io_failure_is_reported_and_hardware_is_restored()
    local state = fixture.new()
    state.failures.read_after_write = state.zone .. "/trip_point_4_temp"
    check.rejected(function() core.new(state.deps):configure(check.thresholds(true)) end, "read")
    check.active_files(state, {40, 50, 65, 80})
    check.only_active_writes(state)
    check.equal(#state.saves, 0)
end

function tests.commit_failure_restores_hardware_and_configuration()
    local state = fixture.new()
    state.failures.commit_once = true
    check.rejected(function() core.new(state.deps):configure(check.thresholds(true)) end, "commit")
    check.active_files(state, {40, 50, 65, 80})
    check.equal(state.get_config().custom, false)
    check.equal(state.get_config().t0, 40)
    check.equal(state.commit_attempts, 2, "failed commit followed by explicit restoration")
    check.only_active_writes(state)
end

function tests.rollback_failure_is_reported_alongside_original_failure()
    local state = fixture.new()
    state.failures.commit = true
    local failure = check.rejected(function()
        core.new(state.deps):configure(check.thresholds(true))
    end, "rollback")
    assert(failure:lower():find("commit", 1, true), "original commit failure must remain visible")
    check.active_files(state, {40, 50, 65, 80})
    check.only_active_writes(state)
end

function tests.successful_commit_with_wrong_readback_is_not_success()
    local state = fixture.new()
    state.failures.commit_readback = true
    check.rejected(function() core.new(state.deps):configure(check.thresholds(true)) end, "readback")
    check.active_files(state, {40, 50, 65, 80})
    check.equal(state.get_config().custom, false)
    check.only_active_writes(state)
end

function tests.rollback_commit_success_with_wrong_readback_is_explicit_failure()
    local state = fixture.new()
    state.failures.rollback_readback = true
    local failure = check.rejected(function()
        core.new(state.deps):configure(check.thresholds(true))
    end, "rollback failed")
    assert(not failure:find("configuration restored", 1, true), "failed rollback must not claim restoration")
    check.equal(state.commit_attempts, 2)
    check.equal(state.get_config().custom, true, "fixture exposes the failed persisted restoration")
    check.active_files(state, {40, 50, 65, 80})
    check.only_active_writes(state)
end

function tests.rollback_commit_success_with_unreadable_uci_is_explicit_failure()
    local state = fixture.new()
    state.failures.rollback_read_failure = true
    local failure = check.rejected(function()
        core.new(state.deps):configure(check.thresholds(true))
    end, "rollback failed")
    assert(failure:find("UCI read failure", 1, true), "rollback read failure context must remain visible")
    assert(not failure:find("configuration restored", 1, true), "unverified rollback must not claim success")
    check.equal(state.commit_attempts, 2)
    check.active_files(state, {40, 50, 65, 80})
    check.only_active_writes(state)
end

return tests
