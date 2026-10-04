"""Environment diagnostics for the optimizer (P00-T03).

``pob2opt doctor`` answers one question: what can this machine actually do
right now? It only *looks*. It never installs, downloads, opens a browser,
starts an OAuth flow, contacts a provider, boots PoB, or changes the working
directory. It never prints a cookie, token or other secret value; provider
credentials are reported as booleans.

Every check is a pure function of explicitly passed inputs so the fixture tests
can build a missing directory, a missing DLL and an incompatible checkout
without touching the real machine.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import json
import os
import platform
import shutil
import struct
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 1

OK = "ok"
MISSING = "missing"
INCOMPATIBLE = "incompatible"
UNKNOWN = "unknown"

EXIT_OK = 0
EXIT_INVALID_REQUEST = 2
EXIT_MISSING_DEPENDENCY = 3

MIN_PYTHON = (3, 10)

#: Files whose absence means "this directory is not a usable PoB2 checkout".
POB_LAYOUT_MARKERS = (
    "runtime/lua51.dll",
    "src/HeadlessWrapper.lua",
    "src/Launch.lua",
    "src/Data",
    "src/TreeData",
)

#: Imports the offline pipeline needs, and what each one is for.
REQUIRED_PACKAGES = (
    ("pob2mcp", "engine bridge and item conversion"),
    ("pob2opt", "optimizer package under test"),
    ("requests", "approved HTTP acquisition"),
    ("jsonschema", "persisted contract validation"),
)
OPTIONAL_PACKAGES = (
    ("mcp", "MCP server entry point (pob2-mcp only)"),
    ("pytest", "development test harness"),
)


@dataclasses.dataclass(frozen=True)
class Check:
    """One named diagnostic result.

    ``blocks`` names the capabilities that are unavailable while this check is
    not ``ok``. ``blocking`` decides whether the process exit code reports a
    missing dependency; informational checks never change the exit code.
    """

    name: str
    status: str
    summary: str
    blocks: tuple[str, ...] = ()
    blocking: bool = True
    data: Mapping[str, Any] = dataclasses.field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "summary": self.summary,
            "blocks": list(self.blocks),
            "blocking": self.blocking,
            "data": dict(self.data),
        }


@dataclasses.dataclass(frozen=True)
class DoctorReport:
    checks: tuple[Check, ...]

    def by_name(self, name: str) -> Check:
        for check in self.checks:
            if check.name == name:
                return check
        raise KeyError(name)

    @property
    def failed_blocking(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.blocking and not c.passed)

    @property
    def exit_code(self) -> int:
        return EXIT_MISSING_DEPENDENCY if self.failed_blocking else EXIT_OK

    @property
    def blocked_capabilities(self) -> tuple[str, ...]:
        seen: list[str] = []
        for check in self.checks:
            if check.passed:
                continue
            for cap in check.blocks:
                if cap not in seen:
                    seen.append(cap)
        return tuple(seen)

    def to_dict(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for check in self.checks:
            counts[check.status] = counts.get(check.status, 0) + 1
        return {
            "schema_version": SCHEMA_VERSION,
            "tool": "pob2opt doctor",
            "checks": [c.to_dict() for c in self.checks],
            "summary": {
                "counts": counts,
                "blocked_capabilities": list(self.blocked_capabilities),
                "blocking_failures": [c.name for c in self.failed_blocking],
            },
            "exit_code": self.exit_code,
        }


# ----------------------------------------------------------------- utilities

def _pe_machine(path: Path) -> str:
    """Architecture recorded in a PE binary's COFF header, or ``unknown``.

    Catches the 32-bit-Python / 64-bit-DLL mismatch before ctypes fails with an
    opaque OSError. Reads a few bytes; it never loads the library.
    """
    try:
        with path.open("rb") as fh:
            if fh.read(2) != b"MZ":
                return "unknown"
            fh.seek(0x3C)
            offset = struct.unpack("<I", fh.read(4))[0]
            fh.seek(offset)
            if fh.read(4) != b"PE\0\0":
                return "unknown"
            machine = struct.unpack("<H", fh.read(2))[0]
    except (OSError, struct.error):
        return "unknown"
    return {0x014C: "x86", 0x8664: "x64", 0xAA64: "arm64"}.get(machine, hex(machine))


def _module_origin(name: str) -> str | None:
    """Where ``name`` would be imported from, without importing it."""
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        return None
    if spec is None:
        return None
    if spec.origin and spec.origin != "namespace":
        return spec.origin
    locations = list(getattr(spec, "submodule_search_locations", None) or [])
    return locations[0] if locations else None


def _is_relative_to(path: Path, other: Path) -> bool:
    try:
        path.resolve().relative_to(other.resolve())
        return True
    except (ValueError, OSError):
        return False


def _nearest_existing(path: Path) -> Path | None:
    for candidate in [path, *path.parents]:
        if candidate.is_dir():
            return candidate
    return None


def repo_root_of(module_file: str | None = None) -> Path:
    """The monorepo root containing this package, assuming the normal layout."""
    here = Path(module_file or __file__).resolve()
    return here.parents[2]


def resolve_pob_root(
    explicit: str | None, env: Mapping[str, str], repo_root: Path
) -> tuple[Path, str]:
    """Resolve the PoB checkout the same way the engine does, and say how."""
    if explicit:
        return Path(explicit).expanduser(), "--pob-root"
    env_value = env.get("POB2_ROOT")
    if env_value:
        return Path(env_value).expanduser(), "POB2_ROOT"
    return repo_root / "external" / "PathOfBuilding-PoE2", "bundled submodule"


# -------------------------------------------------------------------- checks

def check_python_runtime() -> Check:
    bits = struct.calcsize("P") * 8
    data = {
        "version": platform.python_version(),
        "version_info": list(sys.version_info[:3]),
        "implementation": platform.python_implementation(),
        "bits": bits,
        "executable": sys.executable,
        "platform": platform.platform(),
        "minimum_supported": list(MIN_PYTHON),
    }
    if sys.version_info[:2] < MIN_PYTHON:
        return Check(
            "python_runtime", INCOMPATIBLE,
            "Python {} is below the supported minimum {}.{}.".format(
                platform.python_version(), MIN_PYTHON[0], MIN_PYTHON[1]),
            blocks=("offline_pipeline", "engine"), data=data,
        )
    if bits != 64:
        return Check(
            "python_runtime", INCOMPATIBLE,
            "{}-bit Python cannot load PoB's 64-bit lua51.dll.".format(bits),
            blocks=("engine",), data=data,
        )
    return Check(
        "python_runtime", OK,
        "Python {} ({}-bit) {}.".format(
            platform.python_version(), bits, platform.python_implementation()),
        data=data,
    )


def check_packages() -> Check:
    required: dict[str, Any] = {}
    optional: dict[str, Any] = {}
    missing: list[str] = []
    for name, purpose in REQUIRED_PACKAGES:
        origin = _module_origin(name)
        required[name] = {"importable": origin is not None, "origin": origin, "purpose": purpose}
        if origin is None:
            missing.append(name)
    for name, purpose in OPTIONAL_PACKAGES:
        origin = _module_origin(name)
        optional[name] = {"importable": origin is not None, "origin": origin, "purpose": purpose}
    data = {"required": required, "optional": optional}
    if missing:
        return Check(
            "packages", MISSING,
            "Required packages not importable: " + ", ".join(sorted(missing)) + ".",
            blocks=("offline_pipeline",), data=data,
        )
    return Check("packages", OK,
                 "All {} required packages importable.".format(len(required)), data=data)


def check_package_provenance(repo_root: Path) -> Check:
    """Catch the case where ``pob2opt``/``pob2mcp`` import from another checkout.

    Both packages are usually installed editable. If that install points at a
    standalone pre-monorepo directory, every test and every run silently
    exercises different source than the working tree.
    """
    outside: list[str] = []
    detail: dict[str, Any] = {}
    for name in ("pob2mcp", "pob2opt"):
        origin = _module_origin(name)
        inside = bool(origin) and _is_relative_to(Path(origin), repo_root)
        detail[name] = {"origin": origin, "inside_repo": inside}
        if origin and not inside:
            outside.append(name)
    data = {"repo_root": str(repo_root), "packages": detail}
    if any(d["origin"] is None for d in detail.values()):
        return Check("package_provenance", MISSING,
                     "Project packages are not importable; provenance undetermined.",
                     blocks=("offline_pipeline",), data=data)
    if outside:
        return Check(
            "package_provenance", INCOMPATIBLE,
            "Imported from outside this repository: " + ", ".join(outside)
            + ". Reinstall editable from this working tree "
              "(pip install -e ./pob2-mcp -e ./pob2-optimizer), otherwise the "
              "installed copy runs instead of the code under test.",
            blocks=("reproducible_runs",), data=data,
        )
    return Check("package_provenance", OK,
                 "Project packages import from this working tree.", data=data)


def check_pob_directory(pob_root: Path, source: str) -> Check:
    data: dict[str, Any] = {"path": str(pob_root), "resolved_from": source}
    if not pob_root.is_dir():
        return Check(
            "pob_directory", MISSING,
            "No PoB2 checkout at {} (resolved from {}). Set POB2_ROOT or restore "
            "external/PathOfBuilding-PoE2.".format(pob_root, source),
            blocks=("engine",), data=data,
        )
    data["exists"] = True
    return Check("pob_directory", OK,
                 "PoB2 checkout at {} (from {}).".format(pob_root, source), data=data)


def check_pob_runtime(pob_root: Path) -> Check:
    dll = pob_root / "runtime" / "lua51.dll"
    data: dict[str, Any] = {"path": str(dll)}
    if not dll.is_file():
        return Check("pob_runtime_dll", MISSING,
                     "lua51.dll not found at {}; the engine cannot start.".format(dll),
                     blocks=("engine",), data=data)
    data["bytes"] = dll.stat().st_size
    data["architecture"] = _pe_machine(dll)
    host_bits = struct.calcsize("P") * 8
    if data["architecture"] == "x86" and host_bits == 64:
        return Check("pob_runtime_dll", INCOMPATIBLE,
                     "lua51.dll is 32-bit but this Python is 64-bit.",
                     blocks=("engine",), data=data)
    if data["architecture"] == "x64" and host_bits == 32:
        return Check("pob_runtime_dll", INCOMPATIBLE,
                     "lua51.dll is 64-bit but this Python is 32-bit.",
                     blocks=("engine",), data=data)
    return Check("pob_runtime_dll", OK,
                 "lua51.dll present ({}, {} bytes).".format(
                     data["architecture"], data["bytes"]), data=data)


def check_pob_profile(pob_root: Path) -> Check:
    """Layout and version evidence for the selected checkout.

    Reports what the checkout *is*. It does not approve it for a game patch:
    pinning a patch profile and proving PoB compatibility is P02-T02.
    """
    data: dict[str, Any] = {"markers": {}, "version_evidence": {}}
    if not pob_root.is_dir():
        return Check("pob_profile", MISSING,
                     "No checkout selected; compatibility profile undetermined.",
                     blocks=("engine",), data=data)
    absent = []
    for marker in POB_LAYOUT_MARKERS:
        present = (pob_root / marker).exists()
        data["markers"][marker] = present
        if not present:
            absent.append(marker)
    manifest = pob_root / "manifest.xml"
    if manifest.is_file():
        head = manifest.read_text(encoding="utf-8", errors="replace")[:400]
        data["version_evidence"]["manifest_xml_head"] = head.strip().splitlines()[:3]
    git_head = pob_root / ".git" / "HEAD"
    if git_head.is_file():
        data["version_evidence"]["git_head"] = git_head.read_text(
            encoding="utf-8", errors="replace").strip()
    data["patch_profile_approved"] = False
    data["patch_profile_owner"] = "P02-T02"
    if absent:
        return Check("pob_profile", INCOMPATIBLE,
                     "Checkout is missing required PoB2 layout entries: "
                     + ", ".join(absent) + ".",
                     blocks=("engine",), data=data)
    return Check("pob_profile", OK,
                 "Checkout layout matches PoB2; no patch profile is approved yet "
                 "(P02-T02 owns that).", data=data)


def check_pob_catalog(pob_root: Path) -> Check:
    """Evidence that game data (passive tree and Lua data tables) is on disk."""
    data: dict[str, Any] = {}
    if not pob_root.is_dir():
        return Check("pob_catalog", MISSING, "No checkout selected; catalog undetermined.",
                     blocks=("engine", "catalog_export"), data=data)
    tree_dir = pob_root / "src" / "TreeData"
    data_dir = pob_root / "src" / "Data"
    tree_versions = (
        sorted(p.name for p in tree_dir.iterdir() if p.is_dir()) if tree_dir.is_dir() else []
    )
    data_files = sum(1 for _ in data_dir.rglob("*.lua")) if data_dir.is_dir() else 0
    data.update({
        "tree_data_dir": str(tree_dir), "tree_versions": tree_versions,
        "data_dir": str(data_dir), "data_lua_files": data_files,
    })
    if not tree_versions or data_files == 0:
        return Check("pob_catalog", MISSING,
                     "No passive-tree versions or no Data/*.lua files in the checkout.",
                     blocks=("engine", "catalog_export"), data=data)
    return Check("pob_catalog", OK,
                 "{} tree version(s) and {} Data/*.lua files present.".format(
                     len(tree_versions), data_files), data=data)


def check_providers(env: Mapping[str, str], home: Path | None = None) -> Check:
    """Which external providers are *configured*, without contacting any of them.

    Only booleans and non-secret metadata are reported. No value of POESESSID,
    no token, and no cached token content ever appears in the output.
    """
    home = home or Path(os.path.expanduser("~"))
    token_cache = home / ".pob2-mcp" / "token.json"
    providers = {
        "poe_trade": {
            "configured": bool(env.get("POESESSID")),
            "credential": "POESESSID environment variable",
            "credential_present": bool(env.get("POESESSID")),
            "access_status": "unresolved",
            "note": "Website trade endpoints with a session cookie (research F08). "
                    "A supported automated route is decision D01 and is not established.",
        },
        "poe_oauth": {
            "configured": token_cache.is_file(),
            "credential": "cached OAuth token file",
            "credential_present": token_cache.is_file(),
            "token_cache_path": str(token_cache),
            "access_status": "unresolved",
            "note": "Current code authenticates as GGG client id 'pob' (research F09). "
                    "This project must not reuse another application's identity.",
        },
    }
    data = {"providers": providers, "contacted_any_provider": False, "started_oauth": False}
    return Check("providers", UNKNOWN,
                 "Provider access is unresolved (D01/F09); offline work is unaffected.",
                 blocks=("live_market",), blocking=False, data=data)


def check_run_location(run_root: Path) -> Check:
    """Can run bundles be written here?

    Probes the nearest existing ancestor so the diagnostic never creates the run
    directory as a side effect.
    """
    data: dict[str, Any] = {"run_root": str(run_root), "exists": run_root.exists()}
    probe_dir = _nearest_existing(run_root)
    data["probed"] = str(probe_dir) if probe_dir else None
    if probe_dir is None:
        return Check("run_location", MISSING,
                     "No existing parent directory for {}.".format(run_root),
                     blocks=("runs",), data=data)
    data["writable"] = os.access(probe_dir, os.W_OK)
    if not data["writable"]:
        return Check("run_location", INCOMPATIBLE,
                     "{} is not writable; run bundles cannot be stored.".format(probe_dir),
                     blocks=("runs",), data=data)
    try:
        data["free_bytes"] = shutil.disk_usage(probe_dir).free
    except OSError:
        pass
    return Check("run_location", OK,
                 "Run bundles can be written under {}.".format(probe_dir), data=data)


# ------------------------------------------------------------------- collect

def collect(
    *,
    pob_root: str | None = None,
    run_root: str | None = None,
    env: Mapping[str, str] | None = None,
    repo_root: Path | None = None,
    cwd: Path | None = None,
    home: Path | None = None,
) -> DoctorReport:
    """Run every check. Pure with respect to its arguments; no side effects."""
    env = os.environ if env is None else env
    repo_root = repo_root or repo_root_of()
    cwd = cwd or Path.cwd()
    resolved_pob, source = resolve_pob_root(pob_root, env, repo_root)
    runs = Path(run_root).expanduser() if run_root else cwd / "runs"
    return DoctorReport(checks=(
        check_python_runtime(),
        check_packages(),
        check_package_provenance(repo_root),
        check_pob_directory(resolved_pob, source),
        check_pob_runtime(resolved_pob),
        check_pob_profile(resolved_pob),
        check_pob_catalog(resolved_pob),
        check_providers(env, home),
        check_run_location(runs),
    ))


# ----------------------------------------------------------------------- CLI

_STATUS_LABEL = {OK: "ok      ", MISSING: "missing ", INCOMPATIBLE: "INCOMPAT", UNKNOWN: "unknown "}


def render_text(report: DoctorReport) -> str:
    lines = ["pob2opt doctor", ""]
    for check in report.checks:
        label = _STATUS_LABEL.get(check.status, check.status)
        lines.append("  [{}] {}: {}".format(label, check.name, check.summary))
    lines.append("")
    blocked = report.blocked_capabilities
    lines.append("blocked capabilities: " + (", ".join(blocked) if blocked else "none"))
    failures = report.failed_blocking
    if failures:
        lines.append("blocking failures: " + ", ".join(c.name for c in failures))
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pob2opt doctor",
        description="Inspect Python, paths, runtime and selected profile. Reads only: "
                    "never installs, downloads, authenticates or boots PoB.",
    )
    parser.add_argument("--json", action="store_true",
                        help="emit the structured report on stdout")
    parser.add_argument("--pob-root", default=None,
                        help="PoB2 checkout to inspect "
                             "(default: POB2_ROOT, else the bundled submodule)")
    parser.add_argument("--run-root", default=None,
                        help="directory where run bundles would be written (default: ./runs)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:  # argparse already printed the reason
        return EXIT_OK if exc.code in (0, None) else EXIT_INVALID_REQUEST
    cwd_before = os.getcwd()
    report = collect(pob_root=args.pob_root, run_root=args.run_root)
    if args.json:
        json.dump(report.to_dict(), sys.stdout, indent=2, sort_keys=False)
        sys.stdout.write("\n")
        print(render_text(report), file=sys.stderr)
    else:
        print(render_text(report))
    if os.getcwd() != cwd_before:  # pragma: no cover - guards a regression
        raise RuntimeError("doctor changed the working directory")
    return report.exit_code


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
