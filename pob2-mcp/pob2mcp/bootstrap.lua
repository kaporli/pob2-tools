-- Handlers exposed to Python through MCP_dispatch(name, argsJson) -> resultJson
-- Runs inside the PoB2 headless engine, after HeadlessWrapper.lua.

local dkjson = require("dkjson")

local handlers = {}

local function recalc()
	build.buildFlag = true
	runCallback("OnFrame")
end

local DEFAULT_STAT_KEYS = {
	"TotalDPS", "FullDPS", "CombinedDPS", "TotalDot", "WithDotDPS", "AverageDamage",
	"Speed", "CritChance", "CritMultiplier", "HitChance",
	"Life", "LifeUnreserved", "EnergyShield", "Mana", "ManaUnreserved", "Spirit",
	"TotalEHP", "PhysicalMaximumHitTaken", "LightningMaximumHitTaken",
	"FireResist", "ColdResist", "LightningResist", "ChaosResist",
	"Armour", "Evasion", "BlockChance", "SpellBlockChance", "SpellSuppressionChance",
	"EffectiveMovementSpeedMod",
}

local function statSnapshot(output, keys)
	local out = {}
	for _, k in ipairs(keys or DEFAULT_STAT_KEYS) do
		local v = output[k]
		if type(v) == "number" or type(v) == "string" or type(v) == "boolean" then
			out[k] = v
		end
	end
	return out
end

local function buildSummary()
	local spec = build.spec
	local used = spec and spec:CountAllocNodes() or 0
	local mainGroup = build.skillsTab.socketGroupList[build.mainSocketGroup]
	local mainSkillName
	if mainGroup and mainGroup.displaySkillList and mainGroup.mainActiveSkill then
		local s = mainGroup.displaySkillList[mainGroup.mainActiveSkill]
		if s then mainSkillName = s.activeEffect.grantedEffect.name end
	end
	local allocated = 0
	if spec and spec.allocNodes then
		for _ in pairs(spec.allocNodes) do allocated = allocated + 1 end
	end
	local equipped = 0
	for _, slot in pairs(build.itemsTab.slots) do
		local id = slot.selItemId
		if id and id > 0 and build.itemsTab.items[id] then equipped = equipped + 1 end
	end
	return {
		buildName = build.buildName,
		class = spec and spec.curClassName or nil,
		ascendancy = spec and spec.curAscendClassName or nil,
		level = build.characterLevel,
		passivePointsUsed = used,
		mainSocketGroup = build.mainSocketGroup,
		mainSkill = mainSkillName,
		-- P02-T01 counts what survived a load, so a caller never has to infer
		-- "something was imported" from the absence of an error.
		allocatedNodes = allocated,
		equippedItems = equipped,
		socketGroups = #build.skillsTab.socketGroupList,
	}
end

-- ---------------------------------------------------------------- build I/O

handlers.new_build = function(args)
	newBuild()
	return buildSummary()
end

-- PoB reports a document it cannot read by raising a UI prompt and then
-- carrying on with a default level 1 character (observation P00-OBS-01). The
-- prompt is the only signal, so clear it, load, and turn a new one into an
-- error: a failed import must never be indistinguishable from a real build.
local function takePromptMsg()
	local prompt = __mainObject__ and __mainObject__.promptMsg
	if not prompt then return nil end
	__mainObject__.promptMsg = nil
	local text = tostring(prompt):gsub("%^%d", ""):gsub("%^x%x%x%x%x%x%x", "")
	text = text:gsub("Press Enter.*", ""):gsub("%s+", " ")
	return (text:gsub("^%s*(.-)%s*$", "%1"))
end

handlers.load_build_xml = function(args)
	assert(type(args.xml) == "string", "xml required")
	takePromptMsg()
	loadBuildFromXML(args.xml, args.name or "MCP Build")
	local failure = takePromptMsg()
	if failure then
		error("invalid build document: " .. failure, 0)
	end
	recalc()
	return buildSummary()
end

handlers.save_build_xml = function(args)
	return { xml = build:SaveDB("code") }
end

handlers.import_character = function(args)
	assert(type(args.character) == "table", "character (object from GGG character API) required")
	newBuild()
	local charData = args.character
	build.importTab:ImportItemsAndSkills(charData)
	build.importTab:ImportPassiveTreeAndJewels(charData)
	if charData.level then
		build.characterLevel = charData.level
		build.configTab:UpdateLevel()
	end
	recalc()
	return buildSummary()
end

-- ------------------------------------------------------------------- stats

handlers.get_stats = function(args)
	local output = build.calcsTab.mainOutput
	assert(output, "no calculated output; load a build first")
	if args.all then
		local out = {}
		for k, v in pairs(output) do
			local tv = type(v)
			if tv == "number" or tv == "string" or tv == "boolean" then out[k] = v end
		end
		return out
	end
	return statSnapshot(output, args.keys)
end

handlers.get_build_info = function(args)
	return buildSummary()
end

handlers.set_level = function(args)
	assert(type(args.level) == "number", "level required")
	build.characterLevel = args.level
	build.configTab:UpdateLevel()
	recalc()
	return buildSummary()
end

-- ------------------------------------------------------------------ skills

handlers.get_skills = function(args)
	local groups = {}
	for i, group in ipairs(build.skillsTab.socketGroupList) do
		local skills = {}
		for j, s in ipairs(group.displaySkillList or {}) do
			skills[#skills + 1] = {
				index = j,
				name = s.activeEffect.grantedEffect.name,
				id = s.activeEffect.grantedEffect.id,
			}
		end
		local gems = {}
		for _, gem in ipairs(group.gemList or {}) do
			gems[#gems + 1] = {
				name = gem.nameSpec or (gem.gemData and gem.gemData.name),
				level = gem.level,
				quality = gem.quality,
				enabled = gem.enabled,
			}
		end
		groups[#groups + 1] = {
			index = i,
			label = group.displayLabel or group.label,
			enabled = group.enabled,
			slot = group.slot,
			mainActiveSkill = group.mainActiveSkill,
			activeSkills = skills,
			gems = gems,
		}
	end
	return { groups = groups, mainSocketGroup = build.mainSocketGroup }
end

handlers.set_main_skill = function(args)
	local groupIndex = assert(tonumber(args.group), "group index required")
	local group = assert(build.skillsTab.socketGroupList[groupIndex], "no such socket group")
	build.mainSocketGroup = groupIndex
	build.calcsTab.input.skill_number = groupIndex
	if args.skill then
		group.mainActiveSkill = tonumber(args.skill)
		group.mainActiveSkillCalcs = tonumber(args.skill)
	end
	recalc()
	return buildSummary()
end

-- ------------------------------------------------------------------- items

handlers.get_items = function(args)
	local out = {}
	for slotName, slot in pairs(build.itemsTab.slots) do
		local id = slot.selItemId
		if id and id > 0 and build.itemsTab.items[id] then
			local item = build.itemsTab.items[id]
			out[slotName] = {
				id = id,
				name = item.name,
				baseName = item.baseName,
				rarity = item.rarity,
				raw = args.raw and item:BuildRaw() or nil,
			}
		end
	end
	return out
end

handlers.equip_item = function(args)
	assert(type(args.raw) == "string", "raw item text required")
	build.itemsTab:CreateDisplayItemFromRaw(args.raw, true)
	local item = build.itemsTab.displayItem
	assert(item, "could not parse item text")
	build.itemsTab:AddDisplayItem(args.slot ~= nil)
	if args.slot then
		local slot = assert(build.itemsTab.slots[args.slot], "no such slot: " .. tostring(args.slot))
		slot:SetSelItemId(item.id)
		build.itemsTab:PopulateSlots()
	end
	recalc()
	return { itemId = item.id, name = item.name, stats = statSnapshot(build.calcsTab.mainOutput, args.keys) }
end

handlers.test_item = function(args)
	assert(type(args.raw) == "string", "raw item text required")
	assert(type(args.slot) == "string", "slot name required")
	build.itemsTab:CreateDisplayItemFromRaw(args.raw, true)
	local item = build.itemsTab.displayItem
	assert(item, "could not parse item text")
	build.itemsTab:SetDisplayItem() -- clear; do not add to build
	local calcFunc, baseOutput = build.calcsTab:GetMiscCalculator()
	local newOutput = calcFunc({ repSlotName = args.slot, repItem = item })
	local keys = args.keys or DEFAULT_STAT_KEYS
	local diff = {}
	for _, k in ipairs(keys) do
		local b = tonumber(baseOutput[k])
		local n = tonumber(newOutput[k])
		if (b and b ~= 0) or (n and n ~= 0) then
			diff[k] = { base = b or 0, new = n or 0, delta = (n or 0) - (b or 0) }
		end
	end
	return { name = item.name, diff = diff }
end

handlers.convert_trade_item = function(args)
	-- args.item = the `item` object of one trade API fetch result entry
	-- (ported from TradeQueryRequests:FetchResultBlock)
	local item = assert(args.item, "item object required")
	local t_insert = table.insert
	local spirit, armour, evasion, es, charmSlots, quality, radius, limit
	if item.properties then
		for _, property in ipairs(item.properties) do
			local name = escapeGGGString(property.name)
			if name == "Armour" then armour = property.values[1][1]
			elseif name == "Evasion Rating" then evasion = property.values[1][1]
			elseif name == "Energy Shield" then es = property.values[1][1]
			elseif name == "Quality" then quality = property.values[1][1]:sub(2, -2)
			elseif name == "Spirit" then spirit = property.values[1][1]
			elseif name == "Charm Slots" then charmSlots = property.values[1][1]
			elseif name == "Radius" then radius = property.values[1][1]
			elseif name == "Limited to" then limit = property.values[1][1]
			end
		end
	end
	local rawLines = {}
	t_insert(rawLines, "Rarity: " .. item.rarity)
	if item.name ~= "" then t_insert(rawLines, item.name) end
	t_insert(rawLines, item.typeLine)
	if charmSlots then t_insert(rawLines, "Charm Slots: " .. charmSlots) end
	if spirit then t_insert(rawLines, "Spirit: " .. spirit) end
	if armour then t_insert(rawLines, "Armour: " .. armour) end
	if evasion then t_insert(rawLines, "Evasion: " .. evasion) end
	if es then t_insert(rawLines, "Energy Shield: " .. es) end
	if item.ilvl then t_insert(rawLines, "Item Level: " .. item.ilvl) end
	if quality then t_insert(rawLines, "Quality: " .. quality) end
	if item.sockets then
		local socketString = ""
		for _, _ in ipairs(item.sockets) do
			socketString = socketString .. "S "
		end
		socketString = socketString:gsub(" $", "")
		t_insert(rawLines, "Sockets: " .. socketString)
	end
	if item.requirements then
		for _, requirement in ipairs(item.requirements) do
			if requirement.name == "Level" then
				t_insert(rawLines, "LevelReq: " .. requirement.values[1][1])
			end
		end
	end
	if radius then t_insert(rawLines, "Radius: " .. radius) end
	if limit then t_insert(rawLines, "Limited to: " .. limit) end
	item.enchantMods = item.enchantMods or {}
	item.fracturedMods = item.fracturedMods or {}
	item.desecratedMods = item.desecratedMods or {}
	item.craftedMods = item.craftedMods or {}
	item.runeMods = item.runeMods or {}
	item.implicitMods = item.implicitMods or {}
	item.explicitMods = item.explicitMods or {}
	local function processLine(modLine)
		local s = ""
		for flagName, flag in pairs(modLine.flags or {}) do
			if flag then s = s .. string.format("{%s}", flagName) end
		end
		return s .. escapeGGGString(modLine.description or modLine)
	end
	t_insert(rawLines, "Implicits: " .. (#item.enchantMods + #item.runeMods + #item.implicitMods))
	for _, modLine in ipairs(item.enchantMods) do t_insert(rawLines, "{enchant}" .. processLine(modLine)) end
	for _, modLine in ipairs(item.runeMods) do t_insert(rawLines, "{enchant}{rune}" .. processLine(modLine)) end
	for _, modLine in ipairs(item.implicitMods) do t_insert(rawLines, processLine(modLine)) end
	for _, modLine in ipairs(item.explicitMods) do t_insert(rawLines, processLine(modLine)) end
	if item.mirrored then t_insert(rawLines, "Mirrored") end
	if item.doubleCorrupted then t_insert(rawLines, "Twice Corrupted")
	elseif item.corrupted then t_insert(rawLines, "Corrupted") end
	if item.sanctified then t_insert(rawLines, "Sanctified") end
	return { item_string = table.concat(rawLines, "\n") }
end

-- ------------------------------------------------------------------- tree

handlers.get_tree = function(args)
	local spec = build.spec
	local allocated = {}
	for id, node in pairs(spec.allocNodes) do
		allocated[#allocated + 1] = { id = id, name = node.dn, type = node.type }
	end
	return {
		class = spec.curClassName,
		ascendancy = spec.curAscendClassName,
		pointsUsed = spec:CountAllocNodes(),
		allocated = allocated,
	}
end

handlers.alloc_nodes = function(args)
	assert(type(args.ids) == "table", "ids (array of node ids) required")
	for _, id in ipairs(args.ids) do
		local node = assert(build.spec.nodes[id], "no node with id " .. tostring(id))
		if not node.alloc then
			build.spec:AllocNode(node)
		end
	end
	build.spec:BuildAllDependsAndPaths()
	recalc()
	return { pointsUsed = build.spec:CountAllocNodes(), stats = statSnapshot(build.calcsTab.mainOutput, args.keys) }
end

handlers.dealloc_nodes = function(args)
	assert(type(args.ids) == "table", "ids (array of node ids) required")
	for _, id in ipairs(args.ids) do
		local node = assert(build.spec.nodes[id], "no node with id " .. tostring(id))
		if node.alloc then
			build.spec:DeallocNode(node)
		end
	end
	build.spec:BuildAllDependsAndPaths()
	recalc()
	return { pointsUsed = build.spec:CountAllocNodes(), stats = statSnapshot(build.calcsTab.mainOutput, args.keys) }
end

handlers.search_nodes = function(args)
	local query = assert(args.text, "text required"):lower()
	local results = {}
	for id, node in pairs(build.spec.nodes) do
		if node.dn then
			local hay = node.dn:lower()
			if node.sd then
				for _, line in ipairs(node.sd) do
					hay = hay .. "\n" .. line:lower()
				end
			end
			if hay:find(query, 1, true) then
				results[#results + 1] = {
					id = id,
					name = node.dn,
					type = node.type,
					allocated = node.alloc and true or false,
					pathLength = node.pathDist,
					stats = node.sd,
				}
				if #results >= (args.limit or 50) then break end
			end
		end
	end
	return results
end

-- ------------------------------------------------------------------ config

handlers.set_config = function(args)
	assert(type(args.name) == "string", "name required")
	build.configTab.input[args.name] = args.value
	build.configTab:BuildModList()
	recalc()
	return { stats = statSnapshot(build.calcsTab.mainOutput, args.keys) }
end

handlers.get_config = function(args)
	local out = {}
	for k, v in pairs(build.configTab.input) do
		local tv = type(v)
		if tv == "number" or tv == "string" or tv == "boolean" then out[k] = v end
	end
	return out
end

-- ------------------------------------------------------------------- misc

handlers.eval = function(args)
	local fn = assert(loadstring(args.code, "mcp-eval"))
	return fn()
end

-- ---------------------------------------------------------------- dispatch

function MCP_dispatch(name, argsJson)
	local handler = handlers[name]
	if not handler then
		return dkjson.encode({ ok = false, error = "unknown function: " .. tostring(name) })
	end
	local args = dkjson.decode(argsJson) or {}
	local ok, result = pcall(handler, args)
	if not ok then
		return dkjson.encode({ ok = false, error = tostring(result) })
	end
	local encoded, err = dkjson.encode({ ok = true, result = result })
	if not encoded then
		return dkjson.encode({ ok = false, error = "result not JSON-encodable: " .. tostring(err) })
	end
	return encoded
end
