-- Engine-side helpers for pob2-optimizer. Loaded after HeadlessWrapper +
-- bootstrap. All functions are prefixed OPT_.

local dkjson = require("dkjson")

local function recalc()
	build.buildFlag = true
	runCallback("OnFrame")
end

-- Strip character to a blank slate at the given level with a fair benchmark.
function OPT_setup(charLevel, resistPen)
	build.characterLevel = charLevel
	build.configTab:UpdateLevel()
	build.spec:ResetNodes()
	build.spec:BuildAllDependsAndPaths()
	for _, g in ipairs(build.skillsTab.socketGroupList) do g.enabled = false end
	for slotName, slot in pairs(build.itemsTab.slots) do slot:SetSelItemId(0) end
	build.itemsTab:PopulateSlots()
	build.configTab.input["enemyLevel"] = charLevel
	build.configTab.input["resistancePenalty"] = resistPen
	build.configTab:BuildModList()
	recalc()
	return true
end

function OPT_equip(raw, slot)
	build.itemsTab:CreateDisplayItemFromRaw(raw, true)
	local item = build.itemsTab.displayItem
	if not item then return { ok = false, err = "could not parse item" } end
	build.itemsTab:AddDisplayItem(true)
	build.itemsTab.slots[slot]:SetSelItemId(item.id)
	build.itemsTab:PopulateSlots()
	recalc()
	return { ok = true, id = item.id }
end

function OPT_clear_slot(slot)
	build.itemsTab.slots[slot]:SetSelItemId(0)
	build.itemsTab:PopulateSlots()
	recalc()
	return true
end

-- Max gem level whose requirement fits the character level.
local function maxGemLevel(gemName, charLevel)
	for id, gem in pairs(build.data.gems) do
		if gem.name == gemName and gem.grantedEffect and gem.grantedEffect.levels then
			local maxLvl = 0
			for lvl, info in ipairs(gem.grantedEffect.levels) do
				if (info.levelRequirement or 0) <= charLevel then maxLvl = lvl end
			end
			return maxLvl
		end
	end
	return 0
end

-- Add a socket group with one active gem. Disables other groups holding the
-- same gem (PoE2 one-copy rule). Returns the group index.
function OPT_add_group(gemName, charLevel, quality, includeFullDPS)
	for _, og in ipairs(build.skillsTab.socketGroupList) do
		for _, gem in ipairs(og.gemList or {}) do
			if (gem.nameSpec == gemName) or (gem.gemData and gem.gemData.name == gemName) then
				og.enabled = false
			end
		end
	end
	local lvl = maxGemLevel(gemName, charLevel)
	if lvl == 0 then return nil end
	local g = { label = "OPT: " .. gemName, enabled = true, set1 = true, set2 = true,
		includeInFullDPS = includeFullDPS and true or false,
		gemList = { { nameSpec = gemName, level = lvl, quality = quality or 0, enabled = true,
		              count = 1, enableGlobal1 = true, enableGlobal2 = true } } }
	table.insert(build.skillsTab.socketGroupList, g)
	build.skillsTab:ProcessSocketGroup(g)
	recalc()
	return #build.skillsTab.socketGroupList
end

-- Trigger-wrapper group: a meta gem (e.g. Cast on Freeze) with a second active
-- gem socketed inside it. Returns the group index, main skill = the socketed
-- spell as triggered.
function OPT_add_wrapped_group(metaName, innerName, charLevel, quality)
	for _, og in ipairs(build.skillsTab.socketGroupList) do
		for _, gem in ipairs(og.gemList or {}) do
			local n = gem.nameSpec or (gem.gemData and gem.gemData.name)
			if n == metaName or n == innerName then og.enabled = false end
		end
	end
	local metaLvl, innerLvl = 0, 0
	for id, gem in pairs(build.data.gems) do
		if gem.name == metaName or gem.name == innerName then
			local m = 0
			for lvl, info in ipairs(gem.grantedEffect.levels or {}) do
				if (info.levelRequirement or 0) <= charLevel then m = lvl end
			end
			if gem.name == metaName then metaLvl = m else innerLvl = m end
		end
	end
	if metaLvl == 0 or innerLvl == 0 then return nil end
	local g = { label = "OPT: " .. metaName .. " > " .. innerName, enabled = true,
		set1 = true, set2 = true, includeInFullDPS = true,
		gemList = {
			{ nameSpec = metaName, level = metaLvl, quality = 0, enabled = true, count = 1 },
			{ nameSpec = innerName, level = innerLvl, quality = quality or 20, enabled = true,
			  count = 1, enableGlobal1 = true, enableGlobal2 = true },
		} }
	table.insert(build.skillsTab.socketGroupList, g)
	build.skillsTab:ProcessSocketGroup(g)
	build.buildFlag = true
	runCallback("OnFrame")
	return #build.skillsTab.socketGroupList
end

function OPT_remove_group(gi)
	table.remove(build.skillsTab.socketGroupList, gi)
	if build.mainSocketGroup > #build.skillsTab.socketGroupList then
		build.mainSocketGroup = 1
		build.calcsTab.input.skill_number = 1
	end
	recalc()
	return true
end

function OPT_set_main(gi, skillIndex)
	local g = build.skillsTab.socketGroupList[gi]
	if not g then return false end
	build.mainSocketGroup = gi
	build.calcsTab.input.skill_number = gi
	g.mainActiveSkill = skillIndex or 1
	g.mainActiveSkillCalcs = skillIndex or 1
	recalc()
	return true
end

function OPT_metrics()
	local o = build.calcsTab.mainOutput
	return {
		dps = o.CombinedDPS or 0, full = o.FullDPS or 0,
		life = o.Life, ehp = o.TotalEHP,
		spirit = o.Spirit, spiritUnreserved = o.SpiritUnreserved,
		str = o.Str, dex = o.Dex, int = o.Int,
		reqStr = o.ReqStr, reqDex = o.ReqDex, reqInt = o.ReqInt,
		-- clear-speed inputs (AoE coverage + multi-target reach)
		aoeRadius = o.AreaOfEffectRadiusMetres or (o.AreaOfEffectRadius and o.AreaOfEffectRadius / 10) or 0,
		projectiles = o.ProjectileCount or 1,
		pierce = o.PierceCount or 0,
		chain = o.ChainCount or 0,
		speed = o.Speed or 0,
		moveSpeed = o.EffectiveMovementSpeedMod or 1,
	}
end

-- All active gems usable at charLevel, with weapon types and tag info.
function OPT_gems(charLevel)
	local out = {}
	for id, gem in pairs(build.data.gems) do
		local ge = gem.grantedEffect
		if ge and not ge.support and ge.levels then
			local maxLvl = maxGemLevel(gem.name, charLevel)
			if maxLvl > 0 then
				local wt = {}
				if ge.weaponTypes then for k in pairs(ge.weaponTypes) do wt[#wt+1] = k end end
				out[#out+1] = { name = gem.name, maxLvl = maxLvl, weaponTypes = wt,
					tagString = gem.tagString or "",
					minion = gem.tags and gem.tags.minion or false,
					description = (ge.description or ""):sub(1, 400) }
			end
		end
	end
	return out
end

-- Best base name per weapon-type for crafting minimal items.
function OPT_best_base(typeName, charLevel)
	local bestName, bestScore = nil, -1
	for name, b in pairs(build.data.itemBases) do
		if b.type == typeName and (b.req and (b.req.level or 0) or 0) <= charLevel then
			local score = 0
			if b.weapon then
				score = (((b.weapon.PhysicalMin or 0) + (b.weapon.PhysicalMax or 0)) / 2) * (b.weapon.AttackRateBase or 1)
			end
			if score >= bestScore then bestName, bestScore = name, score end
		end
	end
	return bestName
end

-- Greedy support selection for group gi. Uses PoB's own compatibility check
-- and requirement formula. Objective: max(CombinedDPS, FullDPS).
function OPT_support_greedy(gi, sockets, charLevel, attrSlack)
	attrSlack = attrSlack or 40
	local g = build.skillsTab.socketGroupList[gi]
	local function score()
		local o = build.calcsTab.mainOutput
		return math.max(o.CombinedDPS or 0, o.FullDPS or 0)
	end
	local activeSkill = build.calcsTab.mainEnv.player.mainSkill
	local used = {}
	for i, og in ipairs(build.skillsTab.socketGroupList) do
		if i ~= gi and og.enabled then
			for _, gem in ipairs(og.gemList or {}) do
				if gem.gemData and gem.gemData.grantedEffect and gem.gemData.grantedEffect.support then
					used[gem.gemData.name] = true
				end
			end
		end
	end
	local o = build.calcsTab.mainOutput
	local attr = { Str = (o.Str or 0) + attrSlack, Dex = (o.Dex or 0) + attrSlack, Int = (o.Int or 0) + attrSlack }
	local pool = {}
	for id, gem in pairs(build.data.gems) do
		local ge = gem.grantedEffect
		if ge and ge.support and not (gem.tags and gem.tags.lineage) and not used[gem.name] then
			local lvl1 = ge.levels and ge.levels[1]
			local req = lvl1 and lvl1.levelRequirement or 0
			local reqAt = math.max(req, charLevel)
			local okAttr = calcLib.getGemStatRequirement(reqAt, gem.reqStr or 0, true) <= attr.Str
				and calcLib.getGemStatRequirement(reqAt, gem.reqDex or 0, true) <= attr.Dex
				and calcLib.getGemStatRequirement(reqAt, gem.reqInt or 0, true) <= attr.Int
			local okCompat = pcall(function() return calcLib.canGrantedEffectSupportActiveSkill(ge, activeSkill) end)
				and calcLib.canGrantedEffectSupportActiveSkill(ge, activeSkill)
			if req <= charLevel and okAttr and okCompat then pool[#pool+1] = gem.name end
		end
	end
	local existing = 0
	for _, gem in ipairs(g.gemList) do
		if gem.gemData and gem.gemData.grantedEffect and gem.gemData.grantedEffect.support then existing = existing + 1 end
	end
	local chosen = {}
	local cur = score()
	for socket = existing + 1, sockets do
		local bestName, bestScore = nil, cur + 0.01
		for _, name in ipairs(pool) do
			local skip = false
			for _, c in ipairs(chosen) do if c == name then skip = true end end
			if not skip then
				table.insert(g.gemList, { nameSpec = name, level = 1, quality = 0, enabled = true, count = 1 })
				build.skillsTab:ProcessSocketGroup(g)
				recalc()
				local d = score()
				table.remove(g.gemList)
				build.skillsTab:ProcessSocketGroup(g)
				if d > bestScore then bestName, bestScore = name, d end
			end
		end
		if not bestName then recalc(); break end
		table.insert(g.gemList, { nameSpec = bestName, level = 1, quality = 0, enabled = true, count = 1 })
		build.skillsTab:ProcessSocketGroup(g)
		recalc()
		cur = score()
		chosen[#chosen+1] = bestName
	end
	return { chosen = chosen, score = cur }
end

-- Config policy: enumerate config vars scoped (via ifSkill/ifCond) to the
-- currently active skills. Returns entries the Python side can floor/ceiling.
function OPT_scoped_configs()
	local varList = package.loaded["Modules.ConfigOptions"] or require("Modules.ConfigOptions")
	local activeNames = {}
	for _, g in ipairs(build.skillsTab.socketGroupList) do
		if g.enabled then
			for _, s in ipairs(g.displaySkillList or {}) do
				activeNames[s.activeEffect.grantedEffect.name] = true
			end
		end
	end
	-- cross-skill conditions worth including whenever any active skill can use them
	local crossConds = { Empowered = true }
	local out = {}
	for _, v in ipairs(varList) do
		if v.var and (v.type == "check" or v.type == "count" or v.type == "countAllowZero") then
			local scoped = false
			local ifSkill = v.ifSkill
			if type(ifSkill) == "string" then ifSkill = { ifSkill } end
			if ifSkill then
				for _, sn in ipairs(ifSkill) do
					if activeNames[sn] then scoped = true end
				end
			end
			if not scoped and type(v.ifCond) == "string" and crossConds[v.ifCond] then
				scoped = true
			end
			if scoped then
				out[#out+1] = { var = v.var, type = v.type, label = (v.label or ""):gsub("%^%w%w%w%w%w%w%w", ""):gsub("%^%d", "") }
			end
		end
	end
	return out
end

function OPT_set_config(var, value)
	build.configTab.input[var] = value
	build.configTab:BuildModList()
	recalc()
	return true
end

function OPT_save_xml()
	return { xml = build:SaveDB("code") }
end

-- Total minion/companion DPS across ALL enabled minion socket groups. This is
-- the summoner-scaling fix: minion damage lives on mainSkill.minion.output, not
-- the player's mainOutput (which reads 0 for pure summoners).
function OPT_minion_dps()
	local total = 0
	local detail = {}
	local saveGi = build.mainSocketGroup
	for gi, g in ipairs(build.skillsTab.socketGroupList) do
		if g.enabled and g.displaySkillList then
			for si, s in ipairs(g.displaySkillList) do
				if s.minion and s.minion.output then
					build.mainSocketGroup = gi
					build.calcsTab.input.skill_number = gi
					g.mainActiveSkill = si
					g.mainActiveSkillCalcs = si
					build.buildFlag = true
					runCallback("OnFrame")
					-- read from the RECALCULATED main skill, not the stale loop var:
					-- s.minion.output is empty until this skill is the active main
					local active = build.calcsTab.mainEnv.player.mainSkill
					local mo = (active and active.minion and active.minion.output) or s.minion.output or {}
					local dps = mo.CombinedDPS or mo.TotalDPS or 0
					-- minion.output.CombinedDPS is already the summoned minion's DPS;
					-- count is often nil/0 on companions (1 tamed beast) -> default 1
					local count = (active and active.minion and active.minion.count) or s.minion.count
					if not count or count < 1 then count = 1 end
					local ge = s.activeEffect and s.activeEffect.grantedEffect
					local mname = s.minion.minionData and s.minion.minionData.name or "?"
					total = total + dps * count
					detail[#detail+1] = { skill = ge and ge.name or "?", minion = mname,
						dps = dps, count = count, total = dps * count }
				end
			end
		end
	end
	build.mainSocketGroup = saveGi
	build.calcsTab.input.skill_number = saveGi
	build.buildFlag = true
	runCallback("OnFrame")
	return { total = total, detail = detail }
end

-- Delivery-geometry primitives for the current main skill (concentration model).
function OPT_geometry()
	local o = build.calcsTab.mainOutput
	local s = build.calcsTab.mainEnv.player.mainSkill
	local sd = s and s.skillData or {}
	local ae = s and s.activeEffect
	local tags = (ae and ae.gemData and ae.gemData.tagString) or ""
	return {
		tags = tags,
		proj = o.ProjectileCount or 1,
		aoe = o.AreaOfEffectRadiusMetres or (o.AreaOfEffectRadius and o.AreaOfEffectRadius / 10) or 0,
		pierce = o.PierceCount or 0,
		chain = o.ChainCount or 0,
		fork = sd.forkCount or 0,
		maxHitRate = sd.maxHitRatePerEnemy,
		channelling = tags:lower():find("channel") ~= nil,
	}
end

-- Which damage types / tools the current main skill actually uses, so the
-- Python side only enables enemy conditions the build can self-apply.
function OPT_damage_profile()
	local o = build.calcsTab.mainOutput
	local prof = { physical=false, lightning=false, fire=false, cold=false, poison=false, bleed=false }
	-- scan every output key for an element's hit/weapon/average/dps contribution
	for k, v in pairs(o) do
		if type(v) == "number" and v > 0 then
			local kl = tostring(k):lower()
			local relevant = kl:find("onweapon") or kl:find("average") or kl:find("hit") or kl:find("dps") or kl:find("dot")
			if relevant then
				for _, dt in ipairs({"physical","lightning","fire","cold"}) do
					if kl:find(dt) and not kl:find("resist") and not kl:find("taken") and not kl:find("reduction") and not kl:find("maximumhit") then
						prof[dt] = true
					end
				end
			end
		end
	end
	if (o.PoisonDPS or 0) > 0 or (o.TotalPoisonDPS or 0) > 0 then prof.poison = true end
	if (o.BleedDPS or 0) > 0 or (o.TotalBleedDPS or 0) > 0 then prof.bleed = true end
	return prof
end

-- Apply permanent quest bonuses (check-type quest configs) up to the given act.
function OPT_quest_bonuses(maxAct)
	local varList = package.loaded["Modules.ConfigOptions"] or require("Modules.ConfigOptions")
	local n = 0
	for _, v in ipairs(varList) do
		if v.var and v.type == "check" then
			local act = tostring(v.var):match("^questAct ?(%d+)")
			if act and tonumber(act) <= maxAct then
				build.configTab.input[v.var] = true
				n = n + 1
			end
		end
	end
	build.configTab:BuildModList()
	recalc()
	return n
end

-- Per-skill rotation primitives for every enabled socket group.
function OPT_primitives()
	local out = {}
	local saveGi = build.mainSocketGroup
	for gi, g in ipairs(build.skillsTab.socketGroupList) do
		if g.enabled and g.displaySkillList and #g.displaySkillList > 0 then
			build.mainSocketGroup = gi
			build.calcsTab.input.skill_number = gi
			g.mainActiveSkill = 1
			g.mainActiveSkillCalcs = 1
			recalc()
			local o = build.calcsTab.mainOutput
			local s = build.calcsTab.mainEnv.player.mainSkill
			local ge = s and s.activeEffect and s.activeEffect.grantedEffect
			out[#out+1] = {
				group = gi, label = g.label, skill = ge and ge.name or "?",
				avgUse = o.AverageDamage, speed = o.Speed, castTime = o.CastTime or o.Time,
				cooldown = o.Cooldown, duration = o.Duration,
				combined = o.CombinedDPS, poison = o.PoisonDPS, dot = o.TotalDot,
			}
		end
	end
	build.mainSocketGroup = saveGi
	build.calcsTab.input.skill_number = saveGi
	recalc()
	return out
end

return true
