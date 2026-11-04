-- Device-tree structure from askey_sbe1v1k, including all seven native trips.
local M = {}
local THERMAL = "/sys/class/thermal"
local HWMON = "/sys/class/hwmon"
local FDT_MAGIC, FDT_VERSION, FDT_HEADER_SIZE = 0xd00dfeed, 17, 40
local FDT_BEGIN_NODE, FDT_END_NODE, FDT_PROP, FDT_END = 1, 2, 3, 9
local CELL_BYTES, BYTE_BASE = 4, 256
local NATIVE_TRIPS = {
    {name="top_glue-critical", kind="critical", temp=125000},
    {name="crit", kind="critical", temp=110000},
    {name="hot", kind="hot", temp=100000},
    {name="active-high", kind="active", temp=80000, phandle=67, state=3},
    {name="active-med", kind="active", temp=65000, phandle=68, state=2},
    {name="active-low", kind="active", temp=50000, phandle=69, state=1},
    {name="active-silent", kind="active", temp=40000, phandle=70, state=0},
}

local function cell(value)
    local bytes = {}
    for index = CELL_BYTES, 1, -1 do
        bytes[index] = string.char(value % BYTE_BASE)
        value = math.floor(value / BYTE_BASE)
    end
    return table.concat(bytes)
end

local function cells(values)
    local bytes = {}
    for _, value in ipairs(values) do bytes[#bytes + 1] = cell(value) end
    return table.concat(bytes)
end

local function padded(value)
    return value .. string.rep("\0", (CELL_BYTES - #value % CELL_BYTES) % CELL_BYTES)
end

local function node(name, properties, children)
    return {name=name, properties=properties or {}, children=children or {}}
end

local function trip_nodes(trips)
    local nodes = {}
    for _, trip in ipairs(trips) do
        local properties = {
            {"type", trip.kind .. "\0"}, {"temperature", cell(trip.temp)},
            {"hysteresis", cell(1000)},
        }
        if trip.phandle then properties[#properties + 1] = {"phandle", cell(trip.phandle)} end
        nodes[#nodes + 1] = node(trip.name, properties)
    end
    return nodes
end

local function cooling_nodes(trips)
    local nodes = {}
    for _, trip in ipairs(trips) do
        if trip.state then
            nodes[#nodes + 1] = node("cpu-" .. trip.name, {
                {"trip", cell(trip.phandle)},
                {"cooling-device", cells({66, trip.state, trip.state})},
            })
        end
    end
    return nodes
end

local function encode_tree(tree)
    local strings, offsets, size = {}, {}, 0
    local function encode(current)
        local parts = {cell(FDT_BEGIN_NODE), padded(current.name .. "\0")}
        for _, property in ipairs(current.properties) do
            local name, value = property[1], property[2]
            if not offsets[name] then
                offsets[name], size = size, size + #name + 1
                strings[#strings + 1] = name .. "\0"
            end
            parts[#parts + 1] = cells({FDT_PROP, #value, offsets[name]}) .. padded(value)
        end
        for _, child in ipairs(current.children) do parts[#parts + 1] = encode(child) end
        parts[#parts + 1] = cell(FDT_END_NODE)
        return table.concat(parts)
    end
    local structure = encode(tree) .. cell(FDT_END)
    return structure, table.concat(strings)
end

function M.fdt(trips)
    local tree = node("", {{"compatible", "askey,sbe1v1k\0qcom,ipq9574\0"}}, {
        node("pwm-fan", {
            {"compatible", "pwm-fan\0"}, {"phandle", cell(66)},
            {"cooling-levels", cells({36, 72, 128, 255})},
        }),
        node("thermal-zones", {}, {node("top-glue-thermal", {}, {
            node("trips", {}, trip_nodes(trips)),
            node("cooling-maps", {}, cooling_nodes(trips)),
        })}),
    })
    local structure, strings = encode_tree(tree)
    local reservations = string.rep("\0", 16)
    local structure_offset = FDT_HEADER_SIZE + #reservations
    local strings_offset = structure_offset + #structure
    local header = cells({FDT_MAGIC, strings_offset + #strings, structure_offset,
        strings_offset, FDT_HEADER_SIZE, FDT_VERSION, 16, 0, #strings, #structure})
    return header .. reservations .. structure .. strings
end

local function copy(value)
    local result = {}
    for key, item in pairs(value) do result[key] = item end
    return result
end

local function add_zone(files, options)
    local zone = THERMAL .. "/thermal_zone" .. options.zone
    files[zone .. "/type"], files[zone .. "/temp"] = "top-glue-thermal\n", "53750\n"
    files[zone .. "/policy"], files[zone .. "/mode"] = "step_wise\n", "enabled\n"
    for index, trip in ipairs(options.trips) do
        local prefix = zone .. "/trip_point_" .. (index - 1)
        files[prefix .. "_type"] = trip.kind .. "\n"
        files[prefix .. "_temp"] = tostring(trip.temp) .. "\n"
        files[prefix .. "_hyst"] = "1000\n"
    end
    return zone
end

local function add_links(files, options)
    local paths, names = {}, {}
    local cooling = THERMAL .. "/cooling_device" .. options.cooling
    local real = "/sys/devices/virtual/thermal/cooling_device" .. options.cooling
    files[cooling .. "/type"], files[cooling .. "/max_state"] = "pwm-fan\n", "3\n"
    files[cooling .. "/cur_state"] = "1\n"
    files[real .. "/type"], files[real .. "/max_state"] = "pwm-fan\n", "3\n"
    files[real .. "/cur_state"] = "1\n"
    paths[cooling] = real
    for index, trip in ipairs(options.trips) do
        if trip.state then
            local name = "cdev" .. (2 * (trip.state + 1))
            paths[options.zone_path .. "/" .. name] = real
            files[options.zone_path .. "/" .. name .. "_trip_point"] = tostring(index - 1) .. "\n"
            names[#names + 1] = name
        end
    end
    return {paths=paths, names=names, cooling=cooling}
end

local function add_hwmon(files, index)
    local path = HWMON .. "/hwmon" .. index
    files[path .. "/name"], files[path .. "/pwm1"] = "pwmfan\n", "72\n"
    files[path .. "/pwm1_enable"] = "1\n"
    files[HWMON .. "/hwmon0/name"] = "unrelated-sensor\n"
    return path
end

function M.new(settings)
    settings = settings or {}
    local options = {zone=settings.zone or 9, cooling=settings.cooling or 5,
        hwmon=settings.hwmon or 7, trips=settings.trips or NATIVE_TRIPS}
    local files, failures, writes, saves, reads = {}, {}, {}, {}, {}
    options.zone_path = add_zone(files, options)
    local links = add_links(files, options)
    local hwmon = add_hwmon(files, options.hwmon)
    files["/sys/firmware/fdt"] = M.fdt(options.trips)
    files[THERMAL .. "/thermal_zone0/type"] = "unrelated-thermal\n"
    local zone_entries = copy(links.names)
    for path in pairs(files) do
        if path:sub(1, #options.zone_path + 1) == options.zone_path .. "/" then
            zone_entries[#zone_entries + 1] = path:sub(#options.zone_path + 2)
        end
    end
    local directories = {
        [THERMAL] = {"thermal_zone0", "cooling_device" .. options.cooling, "thermal_zone" .. options.zone},
        [HWMON] = {"hwmon0", "hwmon" .. options.hwmon},
        [options.zone_path] = zone_entries,
    }
    local config = {custom=false, t0=40, t1=50, t2=65, t3=80}
    local state = {files=files, failures=failures, writes=writes, saves=saves, reads=reads,
        directories=directories, paths=links.paths, zone=options.zone_path,
        cooling=links.cooling, hwmon=hwmon, lock_count=0, commit_attempts=0, written={}}
    state.get_config = function() return copy(config) end
    state.set_config = function(value) config = copy(value) end
    state.deps = M.dependencies(state)
    return state
end

function M.save_config(state, value)
    state.commit_attempts = state.commit_attempts + 1
    if state.failures.commit_once and state.commit_attempts == 1 then
        return nil, "injected UCI commit failure"
    end
    if state.failures.commit then return nil, "injected UCI commit failure" end
    state.saves[#state.saves + 1] = copy(value)
    if state.failures.commit_readback then return true end
    if state.failures.rollback_readback or
        (state.failures.rollback_read_failure and state.commit_attempts == 1) then
        state.set_config({custom=true, t0=45, t1=55, t2=70, t3=90})
        return true
    end
    state.set_config(value)
    return true
end

function M.dependencies(state)
    local fs = {}
    fs.read = function(path)
        state.reads[#state.reads + 1] = path
        if state.failures.read == path then return nil, "injected read failure" end
        if state.failures.read_after_write == path and state.written[path] then
            return nil, "injected readback read failure"
        end
        return state.files[path], "file not found: " .. path
    end
    fs.write = function(path, value)
        state.writes[#state.writes + 1] = {path=path, value=value}
        if state.failures.write == path then return nil, "injected write failure" end
        if not state.files[path] then return nil, "file not found: " .. path end
        state.written[path] = true
        if state.failures.readback ~= path then state.files[path] = value end
        return true
    end
    fs.list = function(path) return state.directories[path], "directory not found: " .. path end
    fs.realpath = function(path) return state.paths[path], "link not found: " .. path end
    return {fs=fs, config={
        read=function()
            if state.failures.config_read then return nil, "injected UCI read failure" end
            if state.failures.rollback_read_failure and state.commit_attempts > 1 then
                return nil, "injected rollback UCI read failure"
            end
            return state.get_config()
        end,
        save=function(value) return M.save_config(state, value) end,
    }, with_lock=function(callback)
        state.lock_count = state.lock_count + 1
        return callback()
    end}
end

M.native_trips = NATIVE_TRIPS
return M
