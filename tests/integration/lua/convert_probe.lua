-- P00-T04 probe harness for research finding F12.
--
-- Loads the real `convert_trade_item` handler out of pob2-mcp/pob2mcp/bootstrap.lua
-- and runs it on one item table, under a stock LuaJIT. This is NOT the PoB
-- engine: `escapeGGGString` (a PoB global) is replaced by an identity stub and
-- `dkjson` by a stub that is never called, because the handler is pure string
-- assembly over the table it is given. Only the presence or absence of modifier
-- lines is asserted on, which the stubs cannot affect.
--
-- usage: luajit convert_probe.lua <bootstrap.lua> <item_table.lua> [report]
--
-- With the third argument `report`, the probe prints the handler's own
-- completeness report instead of the item string: one `complete=` line, one
-- `emitted <array>=<count>` line per modifier array and one
-- `unsupported <field>` line per field the handler could not place (P02-T05).

local bootstrapPath, itemPath, mode = ...
assert(bootstrapPath and itemPath, "usage: convert_probe.lua <bootstrap.lua> <item_table.lua>")

escapeGGGString = function(s) return tostring(s) end

local realRequire = require
require = function(name)
	if name == "dkjson" then
		return {
			encode = function() error("dkjson.encode must not be reached by this probe") end,
			decode = function() error("dkjson.decode must not be reached by this probe") end,
		}
	end
	return realRequire(name)
end

local fh = assert(io.open(bootstrapPath, "r"))
local source = fh:read("*a")
fh:close()

-- `handlers` is a local of bootstrap.lua's main chunk, so it is still in scope
-- at the end of the chunk; appending a return exposes it without editing the file.
local chunk = assert(loadstring(source .. "\nreturn handlers", "@bootstrap.lua"))
local handlers = chunk()
assert(type(handlers) == "table", "bootstrap.lua did not yield its handler table")
assert(handlers.convert_trade_item, "convert_trade_item handler missing")

local item = assert(loadfile(itemPath))()
local result = handlers.convert_trade_item({ item = item })
if mode == "report" then
	io.write("complete=", tostring(result.complete), "\n")
	local keys = {}
	for key in pairs(result.emitted_mod_counts or {}) do keys[#keys + 1] = key end
	table.sort(keys)
	for _, key in ipairs(keys) do
		io.write("emitted ", key, "=", tostring(result.emitted_mod_counts[key]), "\n")
	end
	local fields = {}
	for _, entry in ipairs(result.unsupported or {}) do fields[#fields + 1] = entry.field end
	table.sort(fields)
	for _, name in ipairs(fields) do io.write("unsupported ", name, "\n") end
	return
end
io.write(result.item_string)
