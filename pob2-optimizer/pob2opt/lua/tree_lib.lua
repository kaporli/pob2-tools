local spec = build.spec

local function dps(out) return out.CombinedDPS or 0 end
local function recalc() build.buildFlag = true; runCallback("OnFrame") end

local function normalCount()
  local n = 0
  for _, node in pairs(spec.allocNodes) do
    if not node.ascendancyName and node.type ~= "ClassStart" then n = n + 1 end
  end
  return n
end

local function snapshot()
  local ids = {}
  for id, node in pairs(spec.allocNodes) do ids[#ids+1] = id end
  return ids
end

local function restore(ids)
  spec:ResetNodes()
  for _, id in ipairs(ids) do
    local node = spec.nodes[id]
    if node then node.alloc = true; spec.allocNodes[id] = node end
  end
  spec:BuildAllDependsAndPaths()
  recalc()
end

-- grow: greedily allocate best-DPS-per-point paths until budget used.
-- Two-tier radius: notables/keystones within 7 first; if nothing improves,
-- widen to maxRadius (long travel across the tree, e.g. caster wheels far
-- from the class start).
local function grow(budget, ascOnly, log, maxRadius)
  maxRadius = maxRadius or 12
  while true do
    local used = 0
    if ascOnly then
      for _, node in pairs(spec.allocNodes) do
        if node.ascendancyName and node.type ~= "AscendClassStart" and not node.isAscendancyStart then used = used + 1 end
      end
    else
      used = normalCount()
    end
    if used >= budget then break end
    spec:BuildAllDependsAndPaths()
    local calcFunc, calcBase = build.calcsTab:GetMiscCalculator()
    local baseDPS = dps(calcBase)
    local best, bestGain, bestPath = nil, 0.001, nil
    for _, radius in ipairs({7, maxRadius}) do
      for id, node in pairs(spec.nodes) do
        local isAsc = node.ascendancyName ~= nil
        local typeOk = node.type == "Notable" or node.type == "Keystone" or node.type == "Normal"
        if not node.alloc and node.path and #node.path > 0 and typeOk
           and (ascOnly == isAsc)
           and not node.isAscendancyStart and node.type ~= "Socket" then
          local pathLen = #node.path
          local distOk = (node.type == "Normal" and pathLen <= 3) or pathLen <= radius
          if distOk and used + pathLen <= budget then
            local addNodes = {}
            for _, pn in ipairs(node.path) do addNodes[pn] = true end
            local out = calcFunc({ addNodes = addNodes })
            local gain = (dps(out) - baseDPS) / pathLen
            if gain > bestGain then best, bestGain, bestPath = node, gain, node.path end
          end
        end
      end
      if best then break end -- found improvement within this radius tier
    end
    if not best then break end
    for i = #bestPath, 1, -1 do
      local pn = bestPath[i]
      if not pn.alloc then spec:AllocNode(pn) end
    end
    spec:BuildAllDependsAndPaths()
    recalc()
    log[#log+1] = string.format("alloc %s (%d pts, %.1f dps/pt) -> dps %.1f",
      best.dn or "?", #bestPath, bestGain, dps(build.calcsTab.mainOutput))
  end
end

-- prune the single least valuable removable subtree; returns points freed or nil
local function pruneWorst(log)
  spec:BuildAllDependsAndPaths()
  local calcFunc, calcBase = build.calcsTab:GetMiscCalculator()
  local baseDPS = dps(calcBase)
  local worstNode, worstLoss, worstCnt = nil, math.huge, 0
  for id, node in pairs(spec.allocNodes) do
    if not node.ascendancyName and node.type ~= "ClassStart" and node.type ~= "Socket" then
      local removeNodes, cnt = {}, 0
      for _, dn in ipairs(node.depends or {}) do removeNodes[dn] = true; cnt = cnt + 1 end
      if cnt == 0 then removeNodes[node] = true; cnt = 1 end
      if cnt <= 6 then
        local out = calcFunc({ removeNodes = removeNodes })
        local loss = (baseDPS - dps(out)) / cnt
        if loss < worstLoss then worstNode, worstLoss, worstCnt = node, loss, cnt end
      end
    end
  end
  if not worstNode then return nil end
  local toRemove = worstNode.depends
  if not toRemove or #toRemove == 0 then toRemove = { worstNode } end
  local before = normalCount()
  for _, dn in ipairs(toRemove) do
    if dn.alloc then spec:DeallocNode(dn) end
  end
  spec:BuildAllDependsAndPaths()
  recalc()
  if normalCount() >= before then return nil end -- nothing actually freed; stop callers' loops
  log[#log+1] = string.format("prune %s (%d pts, %.2f dps/pt lost)", worstNode.dn or "?", worstCnt, worstLoss)
  return worstCnt
end

-- meet attribute requirements by RE-SWITCHING already-allocated attribute
-- travel nodes (grow defaults them to Strength) to the deficient attribute;
-- only allocates new attribute nodes when no switchable ones remain
local ATTR_INDEX = { Strength = 1, Dexterity = 2, Intelligence = 3 }
function MCP_rebalance_attrs(budget, log)
  for iter = 1, 40 do
    recalc()
    local o = build.calcsTab.mainOutput
    local deficits = {
      { name = "Strength",     short = "Str", need = (o.ReqStr or 0) - (o.Str or 0) },
      { name = "Dexterity",    short = "Dex", need = (o.ReqDex or 0) - (o.Dex or 0) },
      { name = "Intelligence", short = "Int", need = (o.ReqInt or 0) - (o.Int or 0) },
    }
    table.sort(deficits, function(a, b) return a.need > b.need end)
    local worst = deficits[1]
    if worst.need <= 0 then
      log[#log+1] = string.format("attrs OK: Str %d/%d Dex %d/%d Int %d/%d",
        o.Str or 0, o.ReqStr or 0, o.Dex or 0, o.ReqDex or 0, o.Int or 0, o.ReqInt or 0)
      return true
    end
    -- surplus per attribute (never switch away below its own requirement + 5)
    local surplus = {
      Strength = (o.Str or 0) - (o.ReqStr or 0),
      Dexterity = (o.Dex or 0) - (o.ReqDex or 0),
      Intelligence = (o.Int or 0) - (o.ReqInt or 0),
    }
    -- find an allocated attribute node currently set to the most-surplus attr
    local bestDonor, bestSurplus = nil, 5
    for id, node in pairs(spec.allocNodes) do
      local treeNode = spec.tree.nodes[id]
      if treeNode and treeNode.isAttribute then
        local cur = node.dn -- "Strength"/"Dexterity"/"Intelligence" after switching
        if cur ~= worst.name and surplus[cur] and surplus[cur] > bestSurplus then
          bestDonor, bestSurplus = id, surplus[cur]
        end
      end
    end
    if bestDonor then
      spec:SwitchAttributeNode(bestDonor, ATTR_INDEX[worst.name])
      spec:BuildAllDependsAndPaths()
      recalc()
      local o2 = build.calcsTab.mainOutput
      log[#log+1] = string.format("switch attr node -> %s: Str %d Dex %d Int %d",
        worst.short, o2.Str or 0, o2.Dex or 0, o2.Int or 0)
    else
      -- no switchable node: allocate the nearest new attribute node
      spec:BuildAllDependsAndPaths()
      local best, bestLen = nil, 99
      for id, node in pairs(spec.nodes) do
        if not node.alloc and node.isAttribute and node.path and #node.path > 0 and #node.path < bestLen then
          best, bestLen = node, #node.path
        end
      end
      if not best then
        log[#log+1] = string.format("attr fix stuck: %s short %d", worst.short, worst.need)
        return false
      end
      while normalCount() + bestLen > budget do
        if not pruneWorst(log) then
          log[#log+1] = string.format("attr fix out of points: %s short %d", worst.short, worst.need)
          return false
        end
      end
      local nid = best.id
      for i = #best.path, 1, -1 do
        local pn = best.path[i]
        if not pn.alloc then spec:AllocNode(pn) end
      end
      spec:SwitchAttributeNode(nid, ATTR_INDEX[worst.name])
      spec:BuildAllDependsAndPaths()
      recalc()
      local o2 = build.calcsTab.mainOutput
      log[#log+1] = string.format("alloc attr node (%d pts) -> %s: Str %d Dex %d Int %d",
        bestLen, worst.short, o2.Str or 0, o2.Dex or 0, o2.Int or 0)
    end
  end
  return false
end

-- kept for compatibility; now delegates to the rebalancer
function MCP_fix_attrs_old(budget, log)
  for iter = 1, 12 do
    recalc()
    local o = build.calcsTab.mainOutput
    local deficits = {
      { name = "Strength",     short = "Str", need = (o.ReqStr or 0) - (o.Str or 0) },
      { name = "Dexterity",    short = "Dex", need = (o.ReqDex or 0) - (o.Dex or 0) },
      { name = "Intelligence", short = "Int", need = (o.ReqInt or 0) - (o.Int or 0) },
    }
    table.sort(deficits, function(a, b) return a.need > b.need end)
    local worst = deficits[1]
    if worst.need <= 0 then return true end
    -- nearest unallocated attribute node
    spec:BuildAllDependsAndPaths()
    local best, bestLen = nil, 99
    for id, node in pairs(spec.nodes) do
      if not node.alloc and node.isAttribute and node.path and #node.path > 0 and #node.path < bestLen then
        best, bestLen = node, #node.path
      end
    end
    if not best then
      log[#log+1] = string.format("attr fix: no attribute node reachable (%s short %d)", worst.short, worst.need)
      return false
    end
    while normalCount() + bestLen > budget do
      if not pruneWorst(log) then return false end
    end
    local pathIds = {}
    for i = #best.path, 1, -1 do
      local pn = best.path[i]
      if not pn.alloc then
        spec:AllocNode(pn)
        if pn.isAttribute then pathIds[#pathIds+1] = pn.id end
      end
    end
    -- switch every attribute node on the path to the needed attribute
    for _, nid in ipairs(pathIds) do
      local tnode = spec.tree.nodes[nid]
      local idx = nil
      for i, opt in ipairs(tnode.options or {}) do
        local label = opt.dn or (opt.sd and opt.sd[1]) or ""
        if tostring(label):find(worst.name) then idx = i end
      end
      if idx then spec:SwitchAttributeNode(nid, idx) end
    end
    spec:BuildAllDependsAndPaths()
    recalc()
    local o2 = build.calcsTab.mainOutput
    log[#log+1] = string.format("attr fix: +%s node(s) (%d pts) -> Str %d/%d Dex %d/%d Int %d/%d",
      worst.short, bestLen, o2.Str or 0, o2.ReqStr or 0, o2.Dex or 0, o2.ReqDex or 0, o2.Int or 0, o2.ReqInt or 0)
  end
  return false
end

function MCP_optimize_tree(budget, ascBudget, swapRounds)
  local log = {}
  -- ascendancy choice
  local classData = spec.tree.classes[spec.curClassId]
  local bestAsc, bestAscDPS, bestAscSnap = nil, -1, nil
  for ascId = 1, #classData.classes do
    spec:SelectAscendClass(ascId)
    spec:BuildAllDependsAndPaths()
    recalc()
    grow(ascBudget, true, log)
    local d = dps(build.calcsTab.mainOutput)
    log[#log+1] = string.format("ascendancy %s -> dps %.1f", classData.classes[ascId].name, d)
    if d > bestAscDPS then
      bestAsc, bestAscDPS, bestAscSnap = ascId, d, snapshot()
    end
  end
  spec:SelectAscendClass(bestAsc)
  restore(bestAscSnap)

  local okGrow, errGrow = pcall(function()
    grow(budget, false, log)
    MCP_rebalance_attrs(budget, log)
  end)
  if not okGrow then log[#log+1] = "grow aborted: " .. tostring(errGrow) end
  local bestDPS = dps(build.calcsTab.mainOutput)
  local bestSnap = snapshot()
  local okSwap, errSwap = pcall(function()
    for round = 1, swapRounds do
      local freed = pruneWorst(log)
      if not freed then break end
      grow(budget, false, log)
      MCP_rebalance_attrs(budget, log)
      local d = dps(build.calcsTab.mainOutput)
      if d > bestDPS + 0.01 then
        bestDPS = d
        bestSnap = snapshot()
        log[#log+1] = string.format("swap round %d improved -> %.1f", round, d)
      else
        restore(bestSnap)
        log[#log+1] = string.format("swap round %d no improvement (%.1f); stop", round, d)
        break
      end
    end
  end)
  if not okSwap then log[#log+1] = "swap loop aborted: " .. tostring(errSwap) end
  restore(bestSnap)
  return { log = log, dps = bestDPS, ascendancy = classData.classes[bestAsc].name,
           points = normalCount() }
end
return true
