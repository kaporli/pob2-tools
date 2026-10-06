"""Pinned citations into the engine's own source (P02-T02).

A few rules the optimizer needs are literals inside PoB functions rather than
rows in a data table: the passive point maximum, the ascendancy point
maximum, the level cap and the support socket limit. They are read here by
matching a pinned pattern against the checkout, so each one carries the file,
the line and the matched text.

A pattern that no longer matches produces no citation. The rule it supports
then becomes a ``DataGap``, which is the point: an upstream change must show
up as a missing rule rather than as a constant that quietly went stale.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True, slots=True)
class Citation:
    """One matched line of engine source, and what it yielded."""

    name: str
    relative_path: str
    line: int
    text: str
    values: tuple[str, ...]
    file_sha256: str

    def payload(self) -> bytes:
        return ("%s:%d\n%s\n" % (self.relative_path, self.line, self.text)
                ).encode("utf-8")

    def value(self, index: int = 0) -> int:
        return int(self.values[index])


#: name -> (relative path, pattern). Each pattern must capture every number
#: the rule needs; a partial match is treated as no match.
PATTERNS: Mapping[str, tuple[str, str]] = {
    "point_maximums": (
        "src/Modules/Build.lua",
        r"local\s+usedMax,\s*ascMax,\s*secondaryAscMax,\s*level,\s*act\s*=\s*"
        r"(\d+)\s*\+\s*maxWeaponSets\s*\+\s*extra,\s*(\d+),\s*(\d+),"),
    "level_cap": (
        "src/Modules/Build.lua",
        r"level\s*=\s*m_min\(m_max\(PointsUsed.*?\),\s*(\d+)\)"),
    "support_socket_limit": (
        "src/Modules/CalcSetup.lua",
        r"if\s+socketedSupportGems\s*>\s*(\d+)\s+then"),
    # The engine's own release, which bounds the game patch its data can
    # possibly describe. Not the game patch: that comes from release.py.
    "engine_release": (
        "changelog.txt",
        r"^VERSION\[([0-9][0-9.a-z]*)\]\[(\d{4})/(\d{2})/(\d{2})\]"),
}


def read_citations(pob_root: str | Path) -> dict[str, Citation]:
    """Every pattern that still matches in ``pob_root``.

    Missing files and unmatched patterns are simply absent from the result.
    The caller turns each absence into a gap; nothing here substitutes a
    remembered value.
    """
    root = Path(pob_root)
    found: dict[str, Citation] = {}
    cache: dict[str, tuple[list[str], str]] = {}
    for name, (relative, pattern) in PATTERNS.items():
        if relative not in cache:
            path = root / relative
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                cache[relative] = ([], "")
            else:
                cache[relative] = (
                    text.splitlines(),
                    hashlib.sha256(text.encode("utf-8")).hexdigest())
        lines, digest = cache[relative]
        regex = re.compile(pattern)
        for number, line in enumerate(lines, start=1):
            match = regex.search(line)
            if match is None:
                continue
            found[name] = Citation(name=name, relative_path=relative,
                                   line=number, text=line.strip(),
                                   values=tuple(match.groups()),
                                   file_sha256=digest)
            break
    return found


def citations_from_payload(
        payload: Mapping[str, Mapping[str, object]]) -> dict[str, Citation]:
    """Rebuild citations captured by an earlier export.

    Used by the offline lane, which replays a capture instead of reading a
    checkout. The capture carries the same fields, so a replayed export and a
    live one produce the same rules.
    """
    out: dict[str, Citation] = {}
    for name, entry in payload.items():
        out[name] = Citation(
            name=name,
            relative_path=str(entry["relative_path"]),
            line=int(entry["line"]),
            text=str(entry["text"]),
            values=tuple(str(v) for v in entry["values"]),
            file_sha256=str(entry["file_sha256"]))
    return out


def citations_to_payload(citations: Mapping[str, Citation]) -> dict:
    return {
        name: {
            "relative_path": citation.relative_path,
            "line": citation.line,
            "text": citation.text,
            "values": list(citation.values),
            "file_sha256": citation.file_sha256,
        }
        for name, citation in sorted(citations.items())
    }
