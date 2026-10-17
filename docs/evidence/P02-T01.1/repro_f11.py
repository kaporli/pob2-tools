"""Bounded reproduction of the F11 sequence that grew to 4 GiB in base-noplugin-s11.

Child (``child JIT ITERATIONS``): one in-process engine, ITERATIONS repeats of
the test_f11 sequence, one progress line per step on stdout.
Parent (``run NAME JIT ITERATIONS [REPEATS]``): runs the child REPEATS times,
samples private bytes every 0.2 s, kills at 3 GiB or 300 s, and appends one
JSON line per child to repro/NAME.jsonl. Every child is kept, pass or fail.

JIT is ``on`` (PoB default) or ``off`` (``jit.off()`` before any step).
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIMIT = int(os.environ.get("REPRO_LIMIT_MB", "3072")) * 2**20
TIME_LIMIT_S = 300

WEAPON = "\n".join(["Rarity: Rare", "Fixture Stave", "Long Quarterstaff", "Quality: 20",
                    "Item Level: 82", "Adds 60 to 90 Physical Damage",
                    "30% increased Attack Speed"])
HELPERS = (HERE.parents[2] / "pob2-optimizer" / "pob2opt" / "lua" / "opt_helpers.lua")


def child(jit, iterations):
    from pob2mcp.engine import Pob2Engine
    engine = Pob2Engine(os.environ["POB2_ROOT"])
    helpers = HELPERS.read_text(encoding="utf-8")
    if jit == "off":
        engine.eval_lua("jit.off(); return true")
    if jit == "gccheck":
        # At CENSUS_MIB of Lua heap (default 1536): record the heap, run a full collection,
        # record it again, remove the hook and let the step continue. A large
        # drop means the growth was uncollected garbage, not live data.
        trace = str(HERE / "repro" / ("gccheck-%d.txt" % os.getpid())).replace("\\", "/")
        engine.eval_lua("""
            local path = %r
            debug.sethook(function()
                local before = collectgarbage("count")
                if before > %d * 1024 then
                    debug.sethook()
                    collectgarbage("collect")
                    local after = collectgarbage("count")
                    local f = io.open(path, "w")
                    f:write(string.format("before %%d MiB after %%d MiB\\n",
                        math.floor(before / 1024), math.floor(after / 1024)))
                    f:write(debug.traceback("at", 2), "\\n")
                    -- Census of every spec PoB holds: node count and the
                    -- per-node tables BuildAllDependsAndPaths rebuilds.
                    local specs = {}
                    if build and build.treeTab and build.treeTab.specList then
                        for i, spec in ipairs(build.treeTab.specList) do specs["list" .. i] = spec end
                    end
                    if build and build.spec then specs.current = build.spec end
                    for name, spec in pairs(specs) do
                        local n, paths, maxPath, deps, maxDeps, longest = 0, 0, 0, 0, 0, nil
                        for id, node in pairs(spec.nodes or {}) do
                            n = n + 1
                            local p = node.path and #node.path or 0
                            paths = paths + p
                            if p > maxPath then maxPath, longest = p, id end
                            local d = node.depends and #node.depends or 0
                            deps = deps + d
                            if d > maxDeps then maxDeps = d end
                        end
                        f:write(string.format("spec %%s nodes=%%d sumPath=%%d maxPath=%%d(%%s) sumDepends=%%d maxDepends=%%d\\n",
                            name, n, paths, maxPath, tostring(longest), deps, maxDeps))
                    end
                    -- Every table reachable from _G and the registry, once.
                    -- Each table is attributed to the path it was first seen
                    -- on; the 25 largest by entry count are written, and the
                    -- entries under each top-level _G key are totalled.
                    local seen, queue, head = {}, {}, 1
                    local function push(t, where)
                        if type(t) == "table" and not seen[t] then
                            seen[t] = where
                            queue[#queue + 1] = t
                        end
                    end
                    seen[queue] = "census"; seen[seen] = "census"
                    for k, v in pairs(_G) do push(v, "_G." .. tostring(k)) end
                    push(debug.getregistry(), "registry")
                    local largest, totals, tables = {}, {}, 0
                    local kinds, kindEntries, modListPaths = {}, {}, {}
                    while head <= #queue do
                        local t = queue[head]; head = head + 1
                        tables = tables + 1
                        local where, n = seen[t], 0
                        for k, v in next, t do
                            n = n + 1
                            if #queue < 60000000 then
                                local short = #where < 120 and (where .. "." .. tostring(k)) or where
                                push(k, short); push(v, short)
                            end
                        end
                        local mt = getmetatable(t)
                        if type(mt) == "table" then push(mt, where .. "<mt>") end
                        local nf = where:match("^_G%%.build%%.latestTree%%.nodes%%.[^%%.]*%%.([^%%.]*%%.?[^%%.]*)")
                        local top = (nf and ("latestTree.nodes.*." .. nf)) or where:match("^_G%%.build%%.[^%%.]*%%.?[^%%.]*") or where:match("^_G%%.[^%%.]*") or where:match("^[^%%.]*")
                        totals[top] = (totals[top] or 0) + n
                        if n > 20000 then largest[#largest + 1] = {n, where} end
                        -- Kind: PoB class name from the metatable, else the
                        -- sorted string keys (first 6) of a plain table.
                        local kind
                        if type(mt) == "table" and type(rawget(mt, "_className")) == "string" then
                            kind = "class " .. rawget(mt, "_className") ..
                                (rawget(mt, "_parent") and " (parent proxy)" or "")
                        else
                            local keys, count = {}, 0
                            for k in next, t do
                                if type(k) == "string" then
                                    count = count + 1
                                    if count <= 6 then keys[#keys + 1] = k end
                                end
                            end
                            table.sort(keys)
                            kind = (#keys == 0) and ("array len~" .. (n < 4 and n or (n < 32 and "4-31" or "32+")))
                                or ("{" .. table.concat(keys, ",") .. (count > 6 and ",..." or "") .. "}")
                        end
                        kinds[kind] = (kinds[kind] or 0) + 1
                        if kind == "class ModList" then
                            local pattern = where:gsub("%%.%%d+", ".#"):sub(1, 160)
                            modListPaths[pattern] = (modListPaths[pattern] or 0) + 1
                        end
                        kindEntries[kind] = (kindEntries[kind] or 0) + n
                    end
                    table.sort(largest, function(a, b) return a[1] > b[1] end)
                    f:write(string.format("census tables=%%d\\n", tables))
                    for i = 1, math.min(25, #largest) do
                        f:write(string.format("largest %%d %%s\\n", largest[i][1], largest[i][2]))
                    end
                    local order = {}
                    for k, v in pairs(totals) do order[#order + 1] = {v, k} end
                    table.sort(order, function(a, b) return a[1] > b[1] end)
                    for i = 1, math.min(40, #order) do
                        f:write(string.format("total %%d %%s\\n", order[i][1], order[i][2]))
                    end
                    local byKind = {}
                    for k, v in pairs(kinds) do byKind[#byKind + 1] = {v, k} end
                    table.sort(byKind, function(a, b) return a[1] > b[1] end)
                    local byPath = {}
                    for k, v in pairs(modListPaths) do byPath[#byPath + 1] = {v, k} end
                    table.sort(byPath, function(a, b) return a[1] > b[1] end)
                    for i = 1, math.min(15, #byPath) do
                        f:write(string.format("modlist %%d at %%s\\n", byPath[i][1], byPath[i][2]))
                    end
                    for i = 1, math.min(30, #byKind) do
                        f:write(string.format("kind %%d tables %%d entries %%s\\n", byKind[i][1],
                            kindEntries[byKind[i][2]], byKind[i][2]))
                    end
                    f:close()
                end
            end, "", 100000)
            return true""" % (trace, int(os.environ.get("CENSUS_MIB", "1536"))))
    if jit == "hook":
        # A count hook stops LuaJIT recording traces, so this is interpreter
        # only, like "off". Above 1.5 GiB of Lua heap it writes the stack and
        # raises; the traceback file is the evidence.
        trace = str(HERE / "repro" / ("hook-%d.txt" % os.getpid())).replace("\\", "/")
        # After the threshold it samples 30 more firings, each with its call
        # chain, then raises.
        engine.eval_lua("""
            local path = %r
            local samples = -1
            local f
            local function frameLocals(level)
                local out, i = {}, 1
                while true do
                    local name, value = debug.getlocal(level, i)
                    if not name then return out end
                    out[name] = value
                    i = i + 1
                end
            end
            debug.sethook(function()
                if samples < 0 and collectgarbage("count") > 1.5 * 1024 * 1024 then
                    samples = 0
                    f = io.open(path, "w")
                    f:write(debug.traceback("runaway: lua heap " ..
                        math.floor(collectgarbage("count") / 1024) .. " MiB", 2), "\\n")
                end
                if samples < 0 then return end
                samples = samples + 1
                local chain = {}
                for level = 2, 30 do
                    local info = debug.getinfo(level, "Sln")
                    if not info then break end
                    chain[#chain + 1] = (info.short_src or "?"):match("[^/]*$") .. ":" ..
                        tostring(info.currentline) .. "(" .. tostring(info.name) .. ")"
                end
                f:write(string.format("sample %%d heap=%%dMiB %%s\\n", samples,
                    math.floor(collectgarbage("count") / 1024), table.concat(chain, " < ")))
                if samples >= 30 then
                    f:close()
                    debug.sethook()
                    error("runaway stopped by diagnostic hook")
                end
            end, "", 100000)
            return true""" % trace)

    def step(i, name, fn, args=None):
        print(json.dumps({"i": i, "step": name, "t": round(time.monotonic(), 3)}), flush=True)
        return (engine.eval_lua(args) if fn == "eval" else engine.call(fn, args or {}))

    for i in range(iterations):
        step(i, "new_build", "new_build")
        nodes = step(i, "search_nodes", "search_nodes", {"text": "projectile damage", "limit": 5})
        ids = [n["id"] for n in nodes[:2]]
        print(json.dumps({"i": i, "nodes": ids}), flush=True)
        step(i, "alloc_nodes", "alloc_nodes", {"ids": ids})
        step(i, "equip_item", "equip_item", {"raw": WEAPON, "slot": "Weapon 1"})
        xml = step(i, "save_build_xml", "save_build_xml")["xml"]
        step(i, "new_build2", "new_build")
        step(i, "load_build_xml", "load_build_xml", {"xml": xml, "name": "import"})
        step(i, "helpers", "eval", helpers)
        step(i, "OPT_setup", "eval", "return OPT_setup(28, 0)")
        info = step(i, "get_build_info", "get_build_info")
        print(json.dumps({"i": i, "done": True, "level": info.get("level")}), flush=True)
    os._exit(0)


def run(name, jit, iterations, repeats):
    from pob2opt.evaluation.memory import process_memory_bytes
    out = HERE / "repro" / ("%s.jsonl" % name)
    out.parent.mkdir(exist_ok=True)
    for r in range(repeats):
        log = HERE / "repro" / ("%s-%d.steps.txt" % (name, r))
        with log.open("w") as stream:
            proc = subprocess.Popen([sys.executable, __file__, "child", jit, str(iterations)],
                                    stdout=stream, stderr=subprocess.STDOUT)
            started, peak, guard = time.monotonic(), 0, None
            while proc.poll() is None:
                used = process_memory_bytes(proc.pid) or 0
                peak = max(peak, used)
                if used > LIMIT or time.monotonic() - started > TIME_LIMIT_S:
                    guard = "memory" if used > LIMIT else "time"
                    proc.kill()
                    break
                time.sleep(0.2)
            proc.wait()
        lines = [l for l in log.read_text(errors="replace").splitlines() if l.startswith("{")]
        steps = [json.loads(l) for l in lines]
        done = sum(1 for s in steps if s.get("done"))
        last = steps[-1] if steps else None
        nodes = [s["nodes"] for s in steps if "nodes" in s]
        record = {"run": name, "repeat": r, "jit": jit, "iterations": iterations,
                  "completed": done, "exit_code": proc.returncode, "guard": guard,
                  "peak_private_bytes": peak,
                  "seconds": round(time.monotonic() - started, 1),
                  "last_step": last, "distinct_node_choices": sorted(
                      {tuple(n) for n in nodes})}
        with out.open("a") as stream:
            stream.write(json.dumps(record) + "\n")
        print(json.dumps(record), flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "child":
        child(sys.argv[2], int(sys.argv[3]))
    else:
        run(sys.argv[2], sys.argv[3], int(sys.argv[4]),
            int(sys.argv[5]) if len(sys.argv) > 5 else 1)
