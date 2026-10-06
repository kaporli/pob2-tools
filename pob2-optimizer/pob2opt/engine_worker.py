"""Per-process PoB2 engine host for optimizer workers.

Each worker process owns one Lua engine (they are single-threaded). The worker
is initialized once with (pob_root, build_xml, char_level, resist_penalty) and
then evaluates screening/pipeline tasks.
"""

from __future__ import annotations

import json
import os
import sys

_LUA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lua")

# resolved at init
ENGINE = None
CHAR_LEVEL = None


class Worker:
    def __init__(self, pob_root: str, mcp_path: str, build_xml: str,
                 char_level: int, resist_penalty: int):
        # pob2-mcp is normally installed (pip install -e ./pob2-mcp); mcp_path is
        # an optional fallback that prepends a source checkout to sys.path.
        if mcp_path:
            sys.path.insert(0, mcp_path)
        from pob2mcp.engine import Pob2Engine

        self.e = Pob2Engine(pob_root)
        self.char_level = char_level
        self.build_xml = build_xml
        self.resist_penalty = resist_penalty
        self.tasks_done = 0
        # Construction loads the build and nothing else. Clearing it is
        # ``create_blank_build``, which the legacy phase pipeline calls
        # explicitly (research F11: the two used to be the same step, so an
        # imported character was always wiped).
        self.load_exact_build()

    def _load_helpers(self):
        for name in ("opt_helpers.lua", "tree_lib.lua"):
            with open(os.path.join(_LUA_DIR, name), encoding="utf-8") as f:
                self.e.eval_lua(f.read())

    def load_exact_build(self, build_xml: str | None = None):
        """Load a build document as it is. Never calls ``OPT_setup``."""
        xml = self.build_xml if build_xml is None else build_xml
        self.e.call("load_build_xml", {"xml": xml, "name": "opt"})
        self._load_helpers()
        return True

    def create_blank_build(self):
        """Clear tree, groups and equipment to get an empty candidate.

        This is the destructive half of the old constructor, kept because the
        legacy phase pipeline searches from a blank character.
        """
        return self.e.eval_lua(
            f"return OPT_setup({self.char_level}, {self.resist_penalty})")

    def maybe_reset(self, every: int = 50):
        """Periodic full reset to shed accumulated items/groups; cheap group
        cleanup happens per task, this bounds long-run state growth."""
        self.tasks_done += 1
        if self.tasks_done % every == 0:
            self.reset()

    # -- primitives -----------------------------------------------------------

    def lua(self, code: str):
        return self.e.eval_lua(code)

    def call(self, fn, args=None):
        return self.e.call(fn, args)

    def reset(self):
        """Fresh blank candidate (cheap relative to engine boot).

        Legacy search state only. After a native crash this is not a recovery
        path: P02-T01's ``EngineAdapter`` replaces the whole process instead.
        """
        self.load_exact_build()
        self.create_blank_build()

    def equip(self, raw: str, slot: str):
        return self.lua(f"return OPT_equip({json.dumps(raw)}, {json.dumps(slot)})")

    def clear_slot(self, slot: str):
        return self.lua(f"return OPT_clear_slot({json.dumps(slot)})")

    def add_group(self, gem: str, quality: int = 0, full_dps: bool = True):
        return self.lua(
            f"return OPT_add_group({json.dumps(gem)}, {self.char_level}, {quality}, {'true' if full_dps else 'false'})")

    def remove_group(self, gi: int):
        return self.lua(f"return OPT_remove_group({gi})")

    def set_main(self, gi: int, skill: int = 1):
        return self.lua(f"return OPT_set_main({gi}, {skill})")

    def metrics(self) -> dict:
        return self.lua("return OPT_metrics()")

    def gems(self) -> list:
        return self.lua(f"return OPT_gems({self.char_level})")

    def best_base(self, type_name: str) -> str:
        return self.lua(f"return OPT_best_base({json.dumps(type_name)}, {self.char_level})")

    def set_config(self, var: str, value):
        if isinstance(value, bool):
            v = "true" if value else "false"
        else:
            v = json.dumps(value)
        return self.lua(f"return OPT_set_config({json.dumps(var)}, {v})")

    def scoped_configs(self) -> list:
        return self.lua("return OPT_scoped_configs()")

    def support_greedy(self, gi: int, sockets: int):
        return self.lua(f"return OPT_support_greedy({gi}, {sockets}, {self.char_level})")

    def optimize_tree(self, points: int, asc_points: int, swap_rounds: int = 12):
        return self.lua(f"return MCP_optimize_tree({points}, {asc_points}, {swap_rounds})")

    def save_xml(self) -> str:
        return self.lua("return OPT_save_xml()")["xml"]


def new_blank_worker(pob_root, mcp_path, build_xml, char_level, resist_penalty):
    """The legacy entry: load the base build, then clear it for searching."""
    worker = Worker(pob_root, mcp_path, build_xml, char_level, resist_penalty)
    worker.create_blank_build()
    return worker


# -- multiprocessing plumbing --------------------------------------------------

def init_worker(pob_root, mcp_path, build_xml, char_level, resist_penalty):
    global ENGINE, CHAR_LEVEL
    # silence the engine's console spam inside workers
    sys.stdout = open(os.devnull, "w")
    ENGINE = new_blank_worker(pob_root, mcp_path, build_xml, char_level,
                              resist_penalty)
    CHAR_LEVEL = char_level


def run_task(task):
    """Dispatch a (kind, payload) task inside a worker. Must be importable."""
    from pob2opt import phases
    kind, payload = task
    fn = getattr(phases, "task_" + kind)
    try:
        return fn(ENGINE, payload)
    except LookupError as exc:
        return {"skip": str(exc), "task": payload}
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        if "not enough memory" in msg or "table overflow" in msg:
            # LuaJIT heap exhausted: rebuild the engine state and retry once
            try:
                ENGINE.reset()
                return fn(ENGINE, payload)
            except Exception as exc2:
                msg = f"{type(exc2).__name__}: {exc2}"
        return {"error": msg, "task": payload}
