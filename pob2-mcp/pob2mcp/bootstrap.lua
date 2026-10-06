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

-- ----------------------------------------------------------------- catalog
-- P02-T02. Typed read-only enumeration of the loaded game data. Every handler
-- below returns the same envelope:
--
--   { table = <name>, total = <rows>, offset = <first row returned>,
--     next_offset = <nil when the page is the last>, rows = { ... } }
--
-- Rows are ordered by a sorted native key so paging is stable and two runs
-- over the same checkout produce the same bytes. Nothing here writes to the
-- build, so a catalog read cannot disturb an evaluation in the same engine.
-- Names are reported as they appear upstream; these handlers never merge two
-- entities that share a display name.

local CATALOG_PAGE_DEFAULT = 500
local CATALOG_PAGE_MAX = 5000

local function catalogPage(args, keys, build_row, name)
	table.sort(keys)
	local total = #keys
	local offset = tonumber(args and args.offset) or 0
	if offset < 0 then offset = 0 end
	local limit = tonumber(args and args.limit) or CATALOG_PAGE_DEFAULT
	if limit < 1 then limit = 1 end
	if limit > CATALOG_PAGE_MAX then limit = CATALOG_PAGE_MAX end
	local rows = {}
	local last = math.min(offset + limit, total)
	for i = offset + 1, last do
		rows[#rows + 1] = build_row(keys[i])
	end
	return {
		table = name,
		total = total,
		offset = offset,
		next_offset = last < total and last or nil,
		rows = rows,
	}
end

local function sortedStrings(t)
	local out = {}
	for _, v in ipairs(t or {}) do out[#out + 1] = tostring(v) end
	table.sort(out)
	return out
end

local function copyScalars(t)
	local out = {}
	for k, v in pairs(t or {}) do
		local tv = type(v)
		if tv == "number" or tv == "string" or tv == "boolean" then out[tostring(k)] = v end
	end
	return out
end

local function requireTree()
	local spec = assert(build.spec, "no active passive spec; load or create a build first")
	return assert(spec.tree, "the active spec has no tree data")
end

handlers.catalog_classes = function(args)
	local tree = requireTree()
	local keys = {}
	for classId in pairs(tree.classes or {}) do keys[#keys + 1] = tonumber(classId) end
	return catalogPage(args, keys, function(classId)
		local cls = tree.classes[classId]
		local ascendancies = {}
		for index, asc in pairs(cls.ascendancies or {}) do
			ascendancies[#ascendancies + 1] = {
				index = tonumber(index),
				id = asc.id,
				name = asc.name,
				flavourText = asc.flavourText,
			}
		end
		table.sort(ascendancies, function(a, b) return (a.index or 0) < (b.index or 0) end)
		return {
			classId = classId,
			name = cls.name,
			base_str = cls.base_str,
			base_dex = cls.base_dex,
			base_int = cls.base_int,
			startNodeId = cls.startNodeId,
			ascendancies = ascendancies,
		}
	end, "classes")
end

handlers.catalog_passive_nodes = function(args)
	local tree = requireTree()
	local keys = {}
	for id, node in pairs(tree.nodes or {}) do
		if tonumber(id) then keys[#keys + 1] = tonumber(id) end
	end
	return catalogPage(args, keys, function(id)
		local node = tree.nodes[id]
		local linked = {}
		for _, other in ipairs(node.linkedId or {}) do
			if tonumber(other) then linked[#linked + 1] = tonumber(other) end
		end
		table.sort(linked)
		return {
			id = tonumber(id),
			name = node.dn,
			stringId = node.stringId,
			type = node.type,
			ascendancyName = node.ascendancyName,
			isAscendancyStart = node.isAscendancyStart and true or false,
			isNotable = node.isNotable and true or false,
			isKeystone = node.type == "Keystone",
			isMastery = node.type == "Mastery",
			isJewelSocket = node.type == "Socket",
			skill = node.skill,
			group = node.g,
			orbit = node.orbit,
			orbitIndex = node.orbitIndex,
			stats = sortedStrings(node.sd),
			linked = linked,
		}
	end, "passive_nodes")
end

handlers.catalog_gems = function(args)
	local keys = {}
	for id in pairs(data.gems or {}) do keys[#keys + 1] = tostring(id) end
	return catalogPage(args, keys, function(id)
		local gem = data.gems[id]
		local effect = gem.grantedEffect
		return {
			id = id,
			name = gem.name,
			baseTypeName = gem.baseTypeName,
			gameId = gem.gameId,
			variantId = gem.variantId,
			gemType = gem.gemType,
			tier = gem.Tier,
			naturalMaxLevel = gem.naturalMaxLevel,
			reqStr = gem.reqStr,
			reqDex = gem.reqDex,
			reqInt = gem.reqInt,
			tagString = gem.tagString,
			tags = sortedStrings((function()
				local list = {}
				for tag, on in pairs(gem.tags or {}) do if on then list[#list + 1] = tag end end
				return list
			end)()),
			grantedEffectId = gem.grantedEffectId,
			isSupport = (effect and effect.support) and true or false,
			grantedEffectName = effect and effect.name or nil,
		}
	end, "gems")
end

handlers.catalog_granted_skills = function(args)
	local keys = {}
	for id in pairs(data.skills or {}) do keys[#keys + 1] = tostring(id) end
	return catalogPage(args, keys, function(id)
		local skill = data.skills[id]
		local levels = 0
		for _ in pairs(skill.levels or {}) do levels = levels + 1 end
		return {
			id = id,
			name = skill.name,
			support = skill.support and true or false,
			hidden = skill.hidden and true or false,
			castTime = skill.castTime,
			modSource = skill.modSource,
			baseFlags = copyScalars(skill.baseFlags),
			skillTypes = sortedStrings((function()
				local list = {}
				for kind, on in pairs(skill.skillTypes or {}) do
					if on then list[#list + 1] = tostring(kind) end
				end
				return list
			end)()),
			levelCount = levels,
		}
	end, "granted_skills")
end

handlers.catalog_item_bases = function(args)
	local keys = {}
	for name in pairs(data.itemBases or {}) do keys[#keys + 1] = tostring(name) end
	return catalogPage(args, keys, function(name)
		local base = data.itemBases[name]
		return {
			name = name,
			type = base.type,
			subType = base.subType,
			socketLimit = base.socketLimit,
			quality = base.quality,
			hidden = base.hidden and true or false,
			implicit = base.implicit,
			req = copyScalars(base.req),
			tags = sortedStrings((function()
				local list = {}
				for tag, on in pairs(base.tags or {}) do if on then list[#list + 1] = tag end end
				return list
			end)()),
			armour = copyScalars(base.armour),
			weapon = copyScalars(base.weapon),
			flask = copyScalars(base.flask),
		}
	end, "item_bases")
end

handlers.catalog_item_modifiers = function(args)
	-- data.itemMods is a table of named mod groups, so the native key is the
	-- pair (group, id). Both are reported; neither alone is unique.
	local keys = {}
	local index = {}
	for group, mods in pairs(data.itemMods or {}) do
		for id in pairs(mods) do
			local key = tostring(group) .. "\0" .. tostring(id)
			keys[#keys + 1] = key
			index[key] = { group = tostring(group), id = tostring(id) }
		end
	end
	return catalogPage(args, keys, function(key)
		local at = index[key]
		local mod = data.itemMods[at.group][at.id]
		local lines = {}
		for i, line in ipairs(mod) do lines[i] = tostring(line) end
		return {
			group = at.group,
			id = at.id,
			type = mod.type,
			affix = mod.affix,
			level = mod.level,
			lines = lines,
			modTags = sortedStrings(mod.modTags),
			statOrder = sortedStrings(mod.statOrder),
			tradeHashes = sortedStrings(mod.tradeHashes),
			weightKey = mod.weightKey,
			weightVal = mod.weightVal,
		}
	end, "item_modifiers")
end

handlers.catalog_slots = function(args)
	local keys = {}
	for name in pairs(build.itemsTab.slots or {}) do keys[#keys + 1] = tostring(name) end
	return catalogPage(args, keys, function(name)
		local slot = build.itemsTab.slots[name]
		return {
			name = name,
			slotName = slot.slotName,
			label = slot.label,
			weaponSet = slot.weaponSet,
			nodeId = slot.nodeId,
			slotNum = slot.slotNum,
			parentSlot = slot.parentSlot and slot.parentSlot.slotName or nil,
			acceptsItemType = slot.weaponSet and "weapon" or nil,
		}
	end, "slots")
end

handlers.catalog_config_variables = function(args)
	-- ConfigOptions is an ordered list of section markers and variables. The
	-- section a variable belongs to is the last marker before it, so the list
	-- is walked in order and each variable keeps its own position.
	local varList = package.loaded["Modules.ConfigOptions"] or require("Modules.ConfigOptions")
	local entries = {}
	local section = nil
	for position, entry in ipairs(varList) do
		if entry.section then
			section = entry.section
		elseif entry.var then
			local options = nil
			if entry.list then
				options = {}
				for i, option in ipairs(entry.list) do
					options[i] = { value = option.val, label = option.label }
				end
			end
			entries[#entries + 1] = {
				var = entry.var,
				position = position,
				section = section,
				type = entry.type,
				label = entry.label,
				ifCond = entry.ifCond,
				ifMinionCond = entry.ifMinionCond,
				ifEnemyCond = entry.ifEnemyCond,
				ifFlag = entry.ifFlag,
				ifSkill = entry.ifSkill,
				ifSkillData = entry.ifSkillData,
				ifSkillList = entry.ifSkillList and sortedStrings(entry.ifSkillList) or nil,
				ifMult = entry.ifMult,
				ifOption = entry.ifOption,
				defaultIndex = entry.defaultIndex,
				defaultState = (type(entry.defaultState) ~= "table"
					and type(entry.defaultState) ~= "function") and entry.defaultState or nil,
				defaultPlaceholderState = (type(entry.defaultPlaceholderState) ~= "table"
					and type(entry.defaultPlaceholderState) ~= "function")
					and entry.defaultPlaceholderState or nil,
				hasApply = entry.apply ~= nil,
				options = options,
			}
		end
	end
	local keys = {}
	local index = {}
	for _, entry in ipairs(entries) do
		local key = string.format("%06d\0%s", entry.position, entry.var)
		keys[#keys + 1] = key
		index[key] = entry
	end
	return catalogPage(args, keys, function(key) return index[key] end, "config_variables")
end

handlers.catalog_rule_sources = function(args)
	-- The upstream facts the character rules are read from. Reported as data,
	-- not as rules: deciding what they mean is the exporter's job, and a fact
	-- that upstream does not carry is absent here rather than filled in.
	local acts = {}
	local running = 0
	for _, quest in ipairs(data.questRewards or {}) do
		if quest.questPoints then
			running = running + quest.questPoints
			acts[#acts + 1] = {
				act = quest.Act,
				type = quest.Type,
				area = quest.Area,
				areaLevel = quest.AreaLevel,
				info = quest.Info,
				stat = quest.Stat,
				questPoints = quest.questPoints,
				cumulativeQuestPoints = running,
			}
		end
	end
	local rewards = {}
	for i, quest in ipairs(data.questRewards or {}) do
		rewards[i] = {
			index = i,
			act = quest.Act,
			type = quest.Type,
			description = quest.Description,
			area = quest.Area,
			areaLevel = quest.AreaLevel,
			info = quest.Info,
			stat = quest.Stat,
			questPoints = quest.questPoints,
			useConfig = quest.useConfig and true or false,
			options = quest.Options and sortedStrings(quest.Options) or nil,
		}
	end
	return {
		table = "rule_sources",
		treeVersion = build.spec and build.spec.treeVersion or nil,
		latestTreeVersion = latestTreeVersion,
		liveTargetVersion = liveTargetVersion,
		treeVersionList = sortedStrings(treeVersionList),
		maxWeaponSetPoints = build.maxWeaponSets,
		maxActs = build.maxActs,
		questPointRewards = acts,
		questRewards = rewards,
		characterConstants = copyScalars(data.characterConstants),
		gameConstants = copyScalars(data.gameConstants),
		misc = copyScalars(data.misc),
		weaponTypeInfo = (function()
			local out = {}
			for name, info in pairs(data.weaponTypeInfo or {}) do
				out[tostring(name)] = copyScalars(info)
			end
			return out
		end)(),
	}
end

-- ---------------------------------------------------------------- legality
-- P02-T03. One read of what the engine holds after an import, so legality is
-- decided against the engine's own state rather than against the document
-- that was handed to it. PoB accepts documents it does not police, so a clean
-- import is not proof of legality.
--
-- Read-only. Nothing here allocates, equips, repairs or recalculates, and
-- nothing here decides anything: it reports allocation, equipment, skills and
-- the calculated pools, and the caller applies the rules.

handlers.legality_state = function(args)
	local spec = assert(build.spec, "no active passive spec; load or create a build first")
	local used, ascUsed, secondaryAscUsed, socketsUsed, weaponSet1Used, weaponSet2Used =
		spec:CountAllocNodes()

	-- Every allocated node id, split into tree and ascendancy. The start
	-- nodes stay in the lists because they are allocated; they are also
	-- named on their own so a caller does not have to recognise them. The
	-- point counts come from the engine's own counter, which excludes them.
	-- A key that is not a number is reported separately rather than coerced,
	-- so nothing is lost silently.
	local allocated, ascendancy, unreadable = {}, {}, {}
	local classStart, ascendancyStart = nil, nil
	for id, node in pairs(spec.allocNodes) do
		local numeric = tonumber(id) or tonumber(node.id)
		if not numeric then
			unreadable[#unreadable + 1] = tostring(id)
		else
			if node.type == "ClassStart" then
				classStart = numeric
			elseif node.type == "AscendClassStart" then
				ascendancyStart = numeric
			end
			if node.ascendancyName then
				ascendancy[#ascendancy + 1] = numeric
			else
				allocated[#allocated + 1] = numeric
			end
		end
	end
	table.sort(allocated)
	table.sort(ascendancy)
	table.sort(unreadable)

	local items = {}
	for slotName, slot in pairs(build.itemsTab.slots) do
		local id = slot.selItemId
		if id and id > 0 and build.itemsTab.items[id] then
			local item = build.itemsTab.items[id]
			local socketCount = 0
			for _ in pairs(item.sockets or {}) do socketCount = socketCount + 1 end
			items[tostring(slotName)] = {
				itemId = id,
				name = item.name,
				title = item.title,
				baseName = item.baseName,
				rarity = item.rarity,
				type = item.type,
				subType = item.base and item.base.subType or nil,
				itemLevel = item.itemLevel,
				corrupted = item.corrupted and true or false,
				requirements = copyScalars(item.requirements),
				sockets = socketCount,
				weaponSet = slot.weaponSet,
				slotNum = slot.slotNum,
			}
		end
	end

	local groups = {}
	for i, group in ipairs(build.skillsTab.socketGroupList) do
		local gems = {}
		for j, gem in ipairs(group.gemList or {}) do
			local gemData = gem.gemId and data.gems and data.gems[gem.gemId] or nil
			local effect = gemData and gemData.grantedEffect or nil
			gems[#gems + 1] = {
				index = j,
				nameSpec = gem.nameSpec,
				gemId = gem.gemId,
				skillId = gem.skillId,
				variantId = gem.variantId,
				level = gem.level,
				quality = gem.quality,
				enabled = gem.enabled and true or false,
				support = (effect and effect.support) and true or false,
				naturalMaxLevel = gemData and gemData.naturalMaxLevel or nil,
			}
		end
		groups[#groups + 1] = {
			index = i,
			label = group.displayLabel or group.label,
			enabled = group.enabled and true or false,
			slot = group.slot,
			source = group.source and tostring(group.source) or nil,
			sourceItem = group.sourceItem
				and tostring(group.sourceItem.name or group.sourceItem.title) or nil,
			sourceNode = group.sourceNode
				and tostring(group.sourceNode.dn or group.sourceNode.id) or nil,
			gems = gems,
		}
	end

	-- The calculated pools and attributes. A value the engine did not
	-- calculate is absent, never zero: an absent total and a total of zero are
	-- different answers and the caller must be able to tell them apart.
	local output = build.calcsTab.mainOutput or {}
	local pools = {}
	for _, pool in ipairs({ "Life", "Mana", "Spirit" }) do
		pools[#pools + 1] = {
			pool = pool,
			total = output[pool],
			reserved = output[pool .. "Reserved"],
			-- Unreserved is the unclamped difference, so it goes negative when
			-- a build reserves more than its pool. Reserved is clamped
			-- upstream and cannot show over-reservation on its own.
			unreserved = output[pool .. "Unreserved"],
		}
	end
	local attributes = {}
	for _, attribute in ipairs({ "Str", "Dex", "Int" }) do
		attributes[#attributes + 1] = { attribute = attribute, value = output[attribute] }
	end

	return {
		buildName = build.buildName,
		class = spec.curClassName,
		classId = spec.curClassId,
		ascendancy = spec.curAscendClassName,
		ascendClassId = spec.curAscendClassId,
		level = build.characterLevel,
		levelAutoMode = build.characterLevelAutoMode and true or false,
		treeVersion = spec.treeVersion,
		allocatedNodes = allocated,
		ascendancyNodes = ascendancy,
		unreadableNodeKeys = unreadable,
		classStartNode = classStart,
		ascendancyStartNode = ascendancyStart,
		pointsUsed = used,
		ascendancyPointsUsed = ascUsed,
		secondaryAscendancyPointsUsed = secondaryAscUsed,
		jewelSocketsUsed = socketsUsed,
		weaponSet1PointsUsed = weaponSet1Used,
		weaponSet2PointsUsed = weaponSet2Used,
		maxWeaponSets = build.maxWeaponSets,
		items = items,
		socketGroups = groups,
		mainSocketGroup = build.mainSocketGroup,
		pools = pools,
		attributes = attributes,
		calculated = build.calcsTab.mainOutput ~= nil,
	}
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
