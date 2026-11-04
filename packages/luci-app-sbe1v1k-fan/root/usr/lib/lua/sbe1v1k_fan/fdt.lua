local M = {}
local CELL, BYTE, MAGIC = 4, 256, 0xd00dfeed
local BEGIN_NODE, END_NODE, PROPERTY, NOP, FINISH = 1, 2, 3, 4, 9
local HEADER_SIZE = 40
local HEADER_OFFSETS = {
    totalsize=5, off_dt_struct=9, off_dt_strings=13,
    size_dt_strings=33, size_dt_struct=37,
}

function M.u32(bytes, offset)
    offset = offset or 1
    assert(type(bytes) == "string" and offset + CELL - 1 <= #bytes,
        "Truncated device-tree integer")
    local value = 0
    for index = offset, offset + CELL - 1 do
        value = value * BYTE + bytes:byte(index)
    end
    return value
end

function M.cells(bytes)
    assert(type(bytes) == "string" and #bytes % CELL == 0, "Invalid device-tree cells")
    local values = {}
    for offset = 1, #bytes, CELL do values[#values + 1] = M.u32(bytes, offset) end
    return values
end

function M.string(bytes)
    assert(type(bytes) == "string" and bytes:sub(-1) == "\0", "Invalid device-tree string")
    return bytes:sub(1, -2)
end

function M.child(node, name)
    for _, child in ipairs(node.children) do
        if child.name == name then return child end
    end
    error("Missing device-tree node: " .. name)
end

local function aligned(offset)
    return math.floor((offset + CELL - 1) / CELL) * CELL
end

local function zero_string(bytes, offset, limit)
    local finish = bytes:find("\0", offset + 1, true)
    assert(finish and finish <= limit, "Unterminated device-tree string")
    return bytes:sub(offset + 1, finish - 1), finish
end

local function header(bytes)
    assert(type(bytes) == "string" and #bytes >= HEADER_SIZE, "Missing or truncated FDT")
    assert(M.u32(bytes) == MAGIC, "Invalid FDT magic")
    local total = M.u32(bytes, HEADER_OFFSETS.totalsize)
    local state = {bytes=bytes, offset=M.u32(bytes, HEADER_OFFSETS.off_dt_struct),
        strings=M.u32(bytes, HEADER_OFFSETS.off_dt_strings)}
    state.strings_end = state.strings + M.u32(bytes, HEADER_OFFSETS.size_dt_strings)
    state.finish = state.offset + M.u32(bytes, HEADER_OFFSETS.size_dt_struct)
    assert(total <= #bytes and state.offset >= HEADER_SIZE and
        state.strings >= HEADER_SIZE and state.finish <= total and
        state.strings_end <= total, "Invalid FDT block bounds")
    return state
end

local function property(state, node)
    local length = M.u32(state.bytes, state.offset + 1)
    local name_offset = M.u32(state.bytes, state.offset + 5)
    state.offset = state.offset + CELL * 2
    assert(state.offset + length <= state.finish, "Truncated FDT property")
    assert(name_offset < state.strings_end - state.strings, "Invalid FDT property name")
    local name = zero_string(state.bytes, state.strings + name_offset, state.strings_end)
    assert(node and node.properties[name] == nil, "Duplicate or misplaced FDT property")
    node.properties[name] = state.bytes:sub(state.offset + 1, state.offset + length)
    state.offset = aligned(state.offset + length)
end

local function begin_node(state, stack)
    local name, finish = zero_string(state.bytes, state.offset, state.finish)
    state.offset = aligned(finish)
    local node = {name=name, properties={}, children={}}
    local parent = stack[#stack]
    if parent then parent.children[#parent.children + 1] = node end
    stack[#stack + 1] = node
    return node
end

function M.parse(bytes)
    local state, stack, root = header(bytes), {}, nil
    while state.offset < state.finish do
        local token = M.u32(bytes, state.offset + 1)
        state.offset = state.offset + CELL
        if token == BEGIN_NODE then
            local node = begin_node(state, stack)
            if #stack == 1 then
                assert(not root, "Multiple FDT roots")
                root = node
            end
        elseif token == END_NODE then
            assert(#stack > 0, "Unbalanced FDT node")
            stack[#stack] = nil
        elseif token == PROPERTY then
            property(state, stack[#stack])
        elseif token == FINISH then
            assert(root and #stack == 0, "Incomplete FDT")
            return root
        else
            assert(token == NOP, "Unknown FDT token")
        end
    end
    error("Missing FDT end token")
end

return M
