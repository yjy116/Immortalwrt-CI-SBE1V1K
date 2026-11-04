local hardware = require "sbe1v1k_fan.hardware"
local M = {}
local STATES, MILLI = 4, 1000

local function values(config)
    return {config.t0, config.t1, config.t2, config.t3}
end

local function validate(config, snapshot)
    assert(type(config) == "table" and type(config.custom) == "boolean", "custom must be boolean")
    local result = {custom=config.custom}
    local ceiling = math.huge
    for _, trip in ipairs(snapshot.protections) do ceiling = math.min(ceiling, trip.temperature) end
    for state = 0, STATES - 1 do
        local key, value = "t" .. state, config["t" .. state]
        assert(type(value) == "number" and value == math.floor(value) and
            math.abs(value) < math.huge, key .. " must be an integer temperature")
        assert(value < ceiling, "Fan thresholds must remain below native protection temperatures")
        if state > 0 then assert(value > result["t" .. (state - 1)], "Fan thresholds must strictly increase") end
        result[key] = value
    end
    return result
end

local function read_config(deps, snapshot)
    local config, problem = deps.config.read()
    assert(config, "Cannot read fan UCI configuration: " .. tostring(problem))
    return validate(config, snapshot)
end

local function save_checked(deps, config, snapshot)
    local saved, problem = deps.config.save(config)
    assert(saved, "Cannot save fan UCI configuration: " .. tostring(problem))
    local stored = read_config(deps, snapshot)
    for key, value in pairs(config) do
        assert(stored[key] == value, "UCI readback differs: " .. key)
    end
end

local function status(config, snapshot)
    return {ok=true, custom=config.custom, configured=values(config),
        active=snapshot.active, defaults=snapshot.defaults, pwm_levels=snapshot.pwm_levels,
        hysteresis=snapshot.hysteresis, temperature=snapshot.temperature, pwm=snapshot.pwm,
        cooling_state=snapshot.cooling_state, policy=snapshot.policy, mode=snapshot.mode,
        protections=snapshot.protections}
end

local function write_checked(fs, path, temperature)
    local result, problem = fs.write(path, string.format("%.0f\n", temperature * MILLI))
    assert(result, "Cannot write " .. path .. ": " .. tostring(problem))
    assert(hardware.number(fs, path) == temperature * MILLI, "Readback mismatch: " .. path)
end

local function ordered_changes(before, target)
    local order = {}
    -- Lower thresholds from low to high, then raise from high to low.
    for state = 1, STATES do
        if target[state] < before[state] then order[#order + 1] = state end
    end
    for state = STATES, 1, -1 do
        if target[state] > before[state] then order[#order + 1] = state end
    end
    return order
end

local function rollback(deps, transaction)
    local failures = {}
    for index = #transaction.changed, 1, -1 do
        local state = transaction.changed[index]
        local ok, problem = pcall(write_checked, deps.fs,
            transaction.before.paths[state], transaction.before.active[state])
        if not ok then failures[#failures + 1] = tostring(problem) end
    end
    if transaction.saved then
        local ok, problem = pcall(save_checked, deps, transaction.old_config, transaction.before)
        if not ok then failures[#failures + 1] = "UCI: " .. tostring(problem) end
    end
    if #failures > 0 then return "rollback failed: " .. table.concat(failures, "; ") end
    return "previous thresholds and configuration restored"
end

local function apply_transaction(deps, transaction)
    local before, config = transaction.before, transaction.config
    assert(before.policy == "step_wise" and before.mode == "enabled",
        "Native step_wise thermal control must remain enabled")
    local target = config.custom and values(config) or before.defaults
    validate({custom=config.custom, t0=target[1], t1=target[2], t2=target[3], t3=target[4]}, before)
    for _, state in ipairs(ordered_changes(before.active, target)) do
        transaction.changed[#transaction.changed + 1] = state
        write_checked(deps.fs, before.paths[state], target[state])
    end
    local after = hardware.snapshot(deps.fs)
    for state = 1, STATES do assert(after.active[state] == target[state], "Final threshold readback differs") end
    if transaction.persist then
        transaction.saved = true
        save_checked(deps, config, after)
    end
    return status(config, after)
end

local function change(deps, payload, persist)
    local before = hardware.snapshot(deps.fs)
    local old_config = read_config(deps, before)
    local config = validate(payload or old_config, before)
    local transaction = {before=before, old_config=old_config, config=config,
        persist=persist, changed={}, saved=false}
    local ok, result = pcall(apply_transaction, deps, transaction)
    if not ok then error(tostring(result) .. "; " .. rollback(deps, transaction)) end
    return result
end

function M.new(deps)
    assert(type(deps) == "table" and type(deps.with_lock) == "function", "Missing backend dependencies")
    return {
        status=function()
            return deps.with_lock(function()
                local snapshot = hardware.snapshot(deps.fs)
                return status(read_config(deps, snapshot), snapshot)
            end)
        end,
        configure=function(_, payload)
            assert(type(payload) == "table", "configure requires a complete payload")
            return deps.with_lock(function() return change(deps, payload, true) end)
        end,
        apply=function()
            return deps.with_lock(function() return change(deps, nil, false) end)
        end,
    }
end

return M
