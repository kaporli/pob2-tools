"""ctypes bridge to the Path of Building 2 headless calculation engine.

Loads PoB2's own patched LuaJIT (runtime/lua51.dll — it has custom syntax
extensions like the ?? operator, so a stock LuaJIT cannot run PoB2), boots
HeadlessWrapper.lua, and exposes a JSON dispatch into bootstrap.lua handlers.
"""

from __future__ import annotations

import ctypes
import json
import os
import threading

LUA_GLOBALSINDEX = -10002

def _default_pob_root() -> str:
    """Locate a PathOfBuilding-PoE2 checkout.

    Priority: the POB2_ROOT env var, then the git submodule bundled with this
    monorepo (``<repo>/external/PathOfBuilding-PoE2``). Falls back to an empty
    string, which produces a clear error in Pob2Engine.__init__.
    """
    env = os.environ.get("POB2_ROOT")
    if env:
        return env
    here = os.path.dirname(os.path.abspath(__file__))  # .../pob2-mcp/pob2mcp
    submodule = os.path.normpath(
        os.path.join(here, "..", "..", "external", "PathOfBuilding-PoE2")
    )
    if os.path.isdir(submodule):
        return submodule
    return ""


DEFAULT_POB_ROOT = _default_pob_root()

_BOOTSTRAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bootstrap.lua")


class PobEngineError(RuntimeError):
    pass


class Pob2Engine:
    def __init__(self, pob_root: str = DEFAULT_POB_ROOT):
        self.pob_root = os.path.abspath(pob_root)
        self.runtime_dir = os.path.join(self.pob_root, "runtime")
        self.src_dir = os.path.join(self.pob_root, "src")
        if not os.path.isfile(os.path.join(self.runtime_dir, "lua51.dll")):
            raise PobEngineError(
                f"lua51.dll not found under {self.runtime_dir}; "
                "set POB2_ROOT to a PathOfBuilding-PoE2 checkout"
            )
        self._lock = threading.Lock()
        os.add_dll_directory(self.runtime_dir)
        lua = ctypes.CDLL(os.path.join(self.runtime_dir, "lua51.dll"))

        lua.luaL_newstate.restype = ctypes.c_void_p
        lua.luaL_openlibs.argtypes = [ctypes.c_void_p]
        lua.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lua.luaL_loadstring.restype = ctypes.c_int
        lua.lua_pcall.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        lua.lua_pcall.restype = ctypes.c_int
        lua.lua_getfield.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p]
        lua.lua_pushlstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
        lua.lua_tolstring.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        lua.lua_tolstring.restype = ctypes.c_void_p
        lua.lua_settop.argtypes = [ctypes.c_void_p, ctypes.c_int]

        self._lua = lua
        self._L = lua.luaL_newstate()
        lua.luaL_openlibs(self._L)

        # PoB loads all of its data files relative to src/
        os.chdir(self.src_dir)
        self._dostring(
            """
            arg = {}
            package.path = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" .. package.path
            package.cpath = "../runtime/?.dll;" .. package.cpath
            -- HeadlessWrapper blocks on io.read if startup fails; don't let it
            io.read = function() return "" end
            """
        )
        self._dostring('dofile("HeadlessWrapper.lua")')
        self._dostring(
            'if __mainObject__.promptMsg then error("PoB startup failed: " '
            ".. tostring(__mainObject__.promptMsg)) end"
        )
        with open(_BOOTSTRAP, "r", encoding="utf-8") as f:
            self._dostring(f.read())

    # -- low level -----------------------------------------------------------

    def _tostring(self, idx: int) -> str:
        size = ctypes.c_size_t()
        ptr = self._lua.lua_tolstring(self._L, idx, ctypes.byref(size))
        if not ptr:
            return ""
        return ctypes.string_at(ptr, size.value).decode("utf-8", errors="replace")

    def _dostring(self, code: str, name: str = "chunk") -> None:
        lua, L = self._lua, self._L
        if lua.luaL_loadstring(L, code.encode("utf-8")) != 0:
            err = self._tostring(-1)
            lua.lua_settop(L, -2)
            raise PobEngineError(f"lua load error: {err}")
        if lua.lua_pcall(L, 0, 0, 0) != 0:
            err = self._tostring(-1)
            lua.lua_settop(L, -2)
            raise PobEngineError(f"lua runtime error: {err}")

    # -- public API ----------------------------------------------------------

    def call(self, fn: str, args: dict | None = None):
        """Invoke a bootstrap.lua handler; returns its decoded result."""
        payload = json.dumps(args or {}).encode("utf-8")
        with self._lock:
            lua, L = self._lua, self._L
            lua.lua_getfield(L, LUA_GLOBALSINDEX, b"MCP_dispatch")
            name = fn.encode("utf-8")
            lua.lua_pushlstring(L, name, len(name))
            lua.lua_pushlstring(L, payload, len(payload))
            if lua.lua_pcall(L, 2, 1, 0) != 0:
                err = self._tostring(-1)
                lua.lua_settop(L, -2)
                raise PobEngineError(err)
            raw = self._tostring(-1)
            lua.lua_settop(L, -2)
        out = json.loads(raw)
        if not out.get("ok"):
            raise PobEngineError(out.get("error", "unknown engine error"))
        return out.get("result")

    def eval_lua(self, code: str):
        """Run arbitrary Lua inside the engine; returns JSON-encodable result."""
        return self.call("eval", {"code": code})
