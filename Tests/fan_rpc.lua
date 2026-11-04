assert(_VERSION == "Lua 5.1", "RPC contracts require Lua 5.1")
local root = assert(arg[1], "repository root argument is required")
package.path = root .. "/packages/luci-app-sbe1v1k-fan/root/usr/lib/lua/?.lua;" .. package.path
-- Model lua-jsonc's ambiguous empty-table encoding at the serialization boundary.
package.preload["luci.jsonc"] = function()
    return {
        stringify=function() return "[]" end,
        parse=function() error("RPC discovery must not consume request JSON") end,
    }
end
package.preload["sbe1v1k_fan.platform"] = function()
    error("RPC discovery must not load hardware or UCI dependencies")
end
package.preload["sbe1v1k_fan.core"] = function()
    error("RPC discovery must not start the hardware service")
end
arg = {"list"}
dofile(root .. "/packages/luci-app-sbe1v1k-fan/root/usr/libexec/rpcd/sbe1v1k.fan")
