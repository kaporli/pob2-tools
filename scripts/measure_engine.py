"""Measure engine cold start, warm reset, evaluation time and peak memory (P00-T04).

Run it explicitly; it is not part of the test suite:

    POB2_ROOT=<checkout> python scripts/measure_engine.py --out docs/evidence/P00/measurements.json

What it reports is what *this* machine did on *this* checkout with *these*
operations. It is not a throughput claim for other hardware, other builds or the
future encounter evaluator. The operations are named in the output so a later
measurement can be compared like for like.

A-B-A verification runs alongside the timings: the same state is evaluated,
changed, and restored, and the full stat snapshots are compared.
"""

from __future__ import annotations

import argparse
import ctypes
import datetime
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "pob2-mcp"))
sys.path.insert(0, str(REPO_ROOT / "pob2-optimizer"))
sys.path.insert(0, str(REPO_ROOT / "tests"))

from engine_helpers import FIXTURE_WEAPON, STRONGER_WEAPON  # noqa: E402

WARM_ITERATIONS = 12
REL_TOLERANCE = 1e-6


# ------------------------------------------------------------------- memory

class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_uint32),
        ("PageFaultCount", ctypes.c_uint32),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def memory_bytes() -> dict[str, int | None]:
    """Working set of this process, via the Win32 API. None off Windows."""
    if os.name != "nt":
        return {"working_set": None, "peak_working_set": None}
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi = ctypes.WinDLL("psapi")
    psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(_ProcessMemoryCounters), ctypes.c_uint32]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int

    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        return {"working_set": None, "peak_working_set": None}
    return {"working_set": counters.WorkingSetSize,
            "peak_working_set": counters.PeakWorkingSetSize}


class _MemoryStatus(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_uint32), ("dwMemoryLoad", ctypes.c_uint32),
                ("ullTotalPhys", ctypes.c_uint64), ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64), ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64), ("ullAvailVirtual", ctypes.c_uint64),
                ("ullAvailExtendedVirtual", ctypes.c_uint64)]


def total_physical_bytes() -> int | None:
    if os.name != "nt":
        return None
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(_MemoryStatus)]
    kernel32.GlobalMemoryStatusEx.restype = ctypes.c_int
    status = _MemoryStatus()
    status.dwLength = ctypes.sizeof(status)
    if not kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return status.ullTotalPhys


# ------------------------------------------------------------------ helpers

def summarize(samples: list[float]) -> dict[str, float | int]:
    ordered = sorted(samples)
    return {
        "count": len(samples),
        "min_s": round(ordered[0], 6),
        "median_s": round(statistics.median(ordered), 6),
        "max_s": round(ordered[-1], 6),
        "mean_s": round(statistics.fmean(ordered), 6),
        "stdev_s": round(statistics.stdev(ordered), 6) if len(ordered) > 1 else 0.0,
    }


def stats_match(first: dict, second: dict) -> bool:
    if set(first) != set(second):
        return False
    for key, value in first.items():
        other = second[key]
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if abs(other - value) > max(abs(value) * REL_TOLERANCE, 1e-9):
                return False
        elif other != value:
            return False
    return True


def checkout_provenance(pob_root: Path) -> dict:
    """Commit and dirty state of the PoB checkout the timings came from.

    A timing without the revision it was measured against cannot be compared
    with a later one.
    """
    info: dict = {"path": str(pob_root)}
    for key, args in (("commit", ["rev-parse", "HEAD"]),
                      ("branch", ["rev-parse", "--abbrev-ref", "HEAD"])):
        try:
            result = subprocess.run(["git", "-C", str(pob_root), *args],
                                    capture_output=True, text=True, timeout=30)
            info[key] = result.stdout.strip() if result.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            info[key] = None
    try:
        result = subprocess.run(["git", "-C", str(pob_root), "status", "--porcelain"],
                                capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            lines = [line for line in result.stdout.splitlines() if line.strip()]
            info["tracked_files_modified"] = sum(
                1 for line in lines if not line.startswith("??"))
            info["untracked_files"] = sum(1 for line in lines if line.startswith("??"))
            info["dirty_tracked_tree"] = info["tracked_files_modified"] > 0
    except (OSError, subprocess.SubprocessError):
        info["dirty_tracked_tree"] = None
    return info


def hardware() -> dict:
    return {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "machine": platform.machine(),
        "logical_cpus": os.cpu_count(),
        "total_physical_bytes": total_physical_bytes(),
        "python": platform.python_version(),
        "python_bits": ctypes.sizeof(ctypes.c_void_p) * 8,
    }


# -------------------------------------------------------------------- main

def measure(pob_root: str) -> dict:
    from pob2mcp.engine import Pob2Engine

    # Worker.reset() reloads both helper files. Measuring only one would be a
    # reduced probe reported under the name of the real operation.
    lua_dir = REPO_ROOT / "pob2-optimizer" / "pob2opt" / "lua"
    helper_names = ("opt_helpers.lua", "tree_lib.lua")
    helpers = [(name, (lua_dir / name).read_text(encoding="utf-8"))
               for name in helper_names]
    opt_helpers = dict(helpers)["opt_helpers.lua"]

    def load_helpers():
        for _, source in helpers:
            engine.eval_lua(source)

    before_boot = memory_bytes()
    started = time.perf_counter()
    engine = Pob2Engine(pob_root)
    cold_start_s = time.perf_counter() - started
    after_boot = memory_bytes()

    engine.call("new_build")
    nodes = engine.call("search_nodes", {"text": "projectile damage", "limit": 5})
    engine.call("alloc_nodes", {"ids": [n["id"] for n in nodes[:2]]})
    engine.call("equip_item", {"raw": FIXTURE_WEAPON, "slot": "Weapon 1"})
    build_xml = engine.call("save_build_xml")["xml"]
    load_helpers()

    # Warm reset: exactly what engine_worker.Worker.reset() does.
    reset_samples: list[float] = []
    for _ in range(WARM_ITERATIONS):
        started = time.perf_counter()
        engine.call("load_build_xml", {"xml": build_xml, "name": "measure"})
        load_helpers()
        engine.eval_lua("return OPT_setup(28, 0)")
        reset_samples.append(time.perf_counter() - started)

    # Representative evaluation: swap the weapon and read the full stat block,
    # which is the smallest unit the current pipeline actually consumes.
    engine.call("load_build_xml", {"xml": build_xml, "name": "measure"})
    eval_samples: list[float] = []
    for index in range(WARM_ITERATIONS):
        raw = STRONGER_WEAPON if index % 2 else FIXTURE_WEAPON
        started = time.perf_counter()
        engine.call("equip_item", {"raw": raw, "slot": "Weapon 1"})
        engine.call("get_stats", {"all": True})
        eval_samples.append(time.perf_counter() - started)

    # A-B-A on the same engine, after all of the above.
    engine.call("load_build_xml", {"xml": build_xml, "name": "aba"})
    engine.call("equip_item", {"raw": FIXTURE_WEAPON, "slot": "Weapon 1"})
    state_a1 = engine.call("get_stats", {"all": True})
    engine.call("equip_item", {"raw": STRONGER_WEAPON, "slot": "Weapon 1"})
    state_b = engine.call("get_stats", {"all": True})
    engine.call("equip_item", {"raw": FIXTURE_WEAPON, "slot": "Weapon 1"})
    state_a2 = engine.call("get_stats", {"all": True})

    peak = memory_bytes()
    return {
        "schema_version": 1,
        "what_this_is": "Timings for the named operations on one machine and one "
                        "PoB checkout. Not a throughput claim for other hardware, "
                        "other builds, or the future encounter evaluator.",
        "measured_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "pob_root": str(pob_root),
        "pob_checkout": checkout_provenance(Path(pob_root)),
        "fixture_identity": {
            "weapon_sha256": hashlib.sha256(FIXTURE_WEAPON.encode()).hexdigest(),
            "stronger_weapon_sha256": hashlib.sha256(STRONGER_WEAPON.encode()).hexdigest(),
            "helper_lua_sha256": {
                name: hashlib.sha256(source.encode()).hexdigest()
                for name, source in helpers
            },
        },
        "hardware": hardware(),
        "operations": {
            "cold_start": {
                "description": "Pob2Engine(pob_root): load lua51.dll, run "
                               "HeadlessWrapper.lua, load bootstrap.lua.",
                "count": 1, "seconds": round(cold_start_s, 6),
            },
            "warm_reset": {
                "description": "load_build_xml + reload opt_helpers.lua and "
                               "tree_lib.lua + OPT_setup, i.e. the exact call "
                               "sequence of engine_worker.Worker.reset().",
                **summarize(reset_samples),
            },
            "evaluation": {
                "description": "equip_item into Weapon 1 + get_stats(all=True).",
                **summarize(eval_samples),
            },
        },
        "memory_bytes": {
            "before_boot": before_boot, "after_boot": after_boot, "peak": peak,
            "boot_delta_working_set": (
                None if after_boot["working_set"] is None
                else after_boot["working_set"] - before_boot["working_set"]),
        },
        "aba_check": {
            "description": "A and B must differ, and A must reproduce exactly.",
            "tolerance_relative": REL_TOLERANCE,
            "b_differs_from_a": state_b["TotalDPS"] != state_a1["TotalDPS"],
            "a_reproduced": stats_match(state_a1, state_a2),
            "a_total_dps": state_a1["TotalDPS"],
            "b_total_dps": state_b["TotalDPS"],
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pob-root", default=os.environ.get("POB2_ROOT"))
    parser.add_argument("--out", default=None, help="write the JSON report here")
    args = parser.parse_args(argv)

    if not args.pob_root:
        print("set POB2_ROOT or pass --pob-root; refusing to guess", file=sys.stderr)
        return 3
    # Resolve before the engine starts: Pob2Engine chdirs into the PoB source
    # tree, so a relative path recorded afterwards would name the wrong place.
    pob_root = Path(args.pob_root).expanduser().resolve()
    if not (pob_root / "runtime" / "lua51.dll").is_file():
        print("no lua51.dll under %s" % (pob_root / "runtime"), file=sys.stderr)
        return 3

    out_path = Path(args.out).resolve() if args.out else None
    report = measure(str(pob_root))
    payload = json.dumps(report, indent=2) + "\n"
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload, encoding="utf-8")
        print("wrote %s" % out_path, file=sys.stderr)
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
