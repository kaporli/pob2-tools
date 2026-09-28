"""Client for the pathofexile.com trade2 API (PoE 2 trade site).

Anonymous access works for search/fetch but is aggressively rate limited and
sits behind Cloudflare; a POESESSID cookie (env POESESSID) improves limits and
gets past some blocks. Requests are throttled and 429s honoured.
"""

from __future__ import annotations

import os
import time

import requests

BASE = "https://www.pathofexile.com"
USER_AGENT = "pob2-mcp/0.1 (Path of Building 2 headless MCP bridge)"


class TradeError(RuntimeError):
    pass


class Trade2Client:
    def __init__(self, poesessid: str | None = None):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Origin": BASE,
                "Referer": BASE + "/trade2/search/poe2",
            }
        )
        sessid = poesessid or os.environ.get("POESESSID")
        if sessid:
            self.session.cookies.set("POESESSID", sessid, domain="www.pathofexile.com")
        self._min_interval = {"search": 2.0, "fetch": 1.0, "misc": 1.0}
        self._last_request: dict[str, float] = {}

    def _request(self, kind: str, method: str, url: str, **kwargs) -> dict:
        wait = self._min_interval[kind] - (time.time() - self._last_request.get(kind, 0))
        if wait > 0:
            time.sleep(wait)
        for attempt in range(3):
            resp = self.session.request(method, url, timeout=30, **kwargs)
            self._last_request[kind] = time.time()
            if resp.status_code == 429:
                retry_after = min(int(resp.headers.get("Retry-After", "10")), 120)
                time.sleep(retry_after)
                continue
            if resp.status_code == 403:
                raise TradeError(
                    "403 from trade API (Cloudflare or auth). Set the POESESSID env var "
                    "to your pathofexile.com session cookie and try again."
                )
            if resp.status_code != 200:
                raise TradeError(f"{method} {url} -> {resp.status_code}: {resp.text[:300]}")
            return resp.json()
        raise TradeError("rate limited three times in a row; back off and retry later")

    def leagues(self) -> list[dict]:
        data = self._request("misc", "GET", f"{BASE}/api/trade2/data/leagues")
        return data.get("result", [])

    def search(self, league: str, query: dict) -> dict:
        """POST a trade2 search. `query` is the full body: {"query": {...}, "sort": {...}}"""
        url = f"{BASE}/api/trade2/search/poe2/{requests.utils.quote(league)}"
        data = self._request("search", "POST", url, json=query)
        if "error" in data:
            raise TradeError(f"trade search error: {data['error']}")
        return data  # {id, complexity, result: [hashes], total}

    def fetch(self, item_ids: list[str], query_id: str) -> list[dict]:
        """Fetch listing details for up to 10 result hashes per request."""
        out: list[dict] = []
        for i in range(0, len(item_ids), 10):
            chunk = ",".join(item_ids[i : i + 10])
            url = f"{BASE}/api/trade2/fetch/{chunk}?query={query_id}&realm=poe2"
            data = self._request("fetch", "GET", url)
            out.extend(x for x in data.get("result", []) if x)
        return out
