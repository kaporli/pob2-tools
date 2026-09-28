"""Ladder-data puller: fetch public PoE2 characters to build a calibration set.

For each ladder character we can (later) import its skill + gear into the engine,
compute predicted DPS, and compare against a proxy for real performance (its
level / depth reached relative to peers on the same skill). Those become
observations for calibration.fit().

The public ladder endpoint may require auth or be unavailable headless; this
module degrades gracefully and reports what it could fetch. It is the data
pipeline for Step 3 — wired but best-effort, since the ranked ladder API access
varies by season.
"""

from __future__ import annotations

import json
import time

LADDER_URL = "https://www.pathofexile.com/api/ladders/poe2"


def fetch_ladder(mcp_path, league="Forbidden Rites", limit=50, log=print):
    import sys
    sys.path.insert(0, mcp_path)
    from pob2mcp.trade import Trade2Client  # reuse its throttled session

    t = Trade2Client()
    out = []
    try:
        url = f"{LADDER_URL}/{league}?limit={min(limit,200)}&offset=0"
        resp = t.session.get(url, timeout=30)
        if resp.status_code != 200:
            log(f"ladder fetch: HTTP {resp.status_code} (ladder API may need auth/season access)")
            return out
        data = resp.json()
        for entry in data.get("entries", []):
            ch = entry.get("character", {})
            out.append({"name": ch.get("name"), "level": ch.get("level"),
                        "class": ch.get("class"), "rank": entry.get("rank"),
                        "account": entry.get("account", {}).get("name")})
    except Exception as exc:
        log(f"ladder fetch failed: {exc}")
    return out


def observations_from_ladder(entries):
    """Placeholder aggregation: without per-character skill imports (which need
    the character API + auth), we can still use ladder DEPTH per class as a weak
    prior. Real per-skill calibration needs the character-items API; documented
    as the next data hookup. Returns [] until that access is wired."""
    return []
