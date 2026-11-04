local M = {}

function M.equal(actual, expected, message)
    assert(actual == expected, (message or "value") .. ": expected " ..
        tostring(expected) .. ", got " .. tostring(actual))
end

function M.sequence(actual, expected, label)
    M.equal(#actual, #expected, label .. " length")
    for index, value in ipairs(expected) do M.equal(actual[index], value, label .. " " .. index) end
end

function M.rejected(callback, fragment)
    local ok, failure = pcall(callback)
    assert(not ok, "invalid operation unexpectedly succeeded")
    assert(type(failure) == "string" and #failure > 0, "error must explain the failure")
    if fragment then
        assert(failure:lower():find(fragment:lower(), 1, true), "missing error context: " .. failure)
    end
    return failure
end

function M.thresholds(custom)
    return {custom=custom, t0=42, t1=54, t2=67, t3=88}
end

function M.active_files(state, values)
    for index, value in ipairs(values) do
        local path = state.zone .. "/trip_point_" .. (7 - index) .. "_temp"
        M.equal(tonumber(state.files[path]), value * 1000, "active trip " .. index)
    end
end

function M.only_active_writes(state)
    local allowed = {}
    for _, index in ipairs({3, 4, 5, 6}) do
        allowed[state.zone .. "/trip_point_" .. index .. "_temp"] = true
    end
    for _, write in ipairs(state.writes) do
        assert(allowed[write.path], "unexpected hardware write: " .. write.path)
    end
    M.equal(tonumber(state.files[state.zone .. "/trip_point_0_temp"]), 125000)
    M.equal(tonumber(state.files[state.zone .. "/trip_point_1_temp"]), 110000)
    M.equal(tonumber(state.files[state.zone .. "/trip_point_2_temp"]), 100000)
    M.equal(state.files[state.zone .. "/policy"], "step_wise\n")
    M.equal(state.files[state.hwmon .. "/pwm1"], "72\n")
end

return M
