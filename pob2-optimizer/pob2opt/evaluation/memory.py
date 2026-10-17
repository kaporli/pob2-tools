"""Worker memory measurement (P02-T01.1).

The coordinator bounds each worker's memory by sampling it from outside, so a
runaway allocation inside native code is still seen while the worker is busy.

What is measured: private committed bytes on Windows (memory the process has
claimed from the system, paged in or not), resident bytes on Linux. Other
platforms have no probe; a caller asking for a limit there gets an explicit
refusal rather than an unbounded worker.
"""

from __future__ import annotations

import os
import sys

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    class _Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                    ("PrivateUsage", ctypes.c_size_t)]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.K32GetProcessMemoryInfo.restype = wintypes.BOOL
    _kernel32.K32GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_Counters), wintypes.DWORD]

    def process_memory_bytes(pid: int) -> int | None:
        """Private committed bytes of ``pid``, or None if it cannot be read."""
        handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION,
                                       False, int(pid))
        if not handle:
            return None
        try:
            counters = _Counters()
            counters.cb = ctypes.sizeof(_Counters)
            if not _kernel32.K32GetProcessMemoryInfo(
                    handle, ctypes.byref(counters), counters.cb):
                return None
            return int(counters.PrivateUsage)
        finally:
            _kernel32.CloseHandle(handle)

    PROBE = "windows private bytes"

elif sys.platform.startswith("linux"):
    _PAGE = os.sysconf("SC_PAGE_SIZE")

    def process_memory_bytes(pid: int) -> int | None:
        """Resident bytes of ``pid``, or None if it cannot be read."""
        try:
            with open("/proc/%d/statm" % int(pid), "r") as handle:
                return int(handle.read().split()[1]) * _PAGE
        except (OSError, ValueError, IndexError):
            return None

    PROBE = "linux resident bytes"

else:
    def process_memory_bytes(pid: int) -> int | None:
        return None

    PROBE = None


def probe_available() -> bool:
    return PROBE is not None
