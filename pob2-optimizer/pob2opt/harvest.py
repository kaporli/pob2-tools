"""Trade harvest: best in-budget weapons (rare + unique) per category, keyed by
the PoB weapon type names used in phases.py. Single-process (rate limits)."""

from __future__ import annotations

import json
import sys
import time

CATEGORIES = {  # PoB type name -> trade category, martial?
    "Spear": ("weapon.spear", True),
    "Quarterstaff": ("weapon.warstaff", True),
    "Bow": ("weapon.bow", True),
    "Crossbow": ("weapon.crossbow", True),
    "One Hand Mace": ("weapon.onemace", True),
    "Two Hand Mace": ("weapon.twomace", True),
    "Wand": ("weapon.wand", False),
    "Staff": ("weapon.staff", False),
    "Sceptre": ("weapon.sceptre", False),
}
SPELL_LEVELS = "explicit.stat_124131830"
MINION_LEVELS = "explicit.stat_2162097452"
ALL_LEVELS = "explicit.stat_4283407333"


def harvest(engine_worker, league: str, char_level: int, price_cap: float,
            per_cat: int = 8, log=print):
    sys.path.insert(0, engine_worker)  # engine_worker is the pob2-mcp path here
    from pob2mcp.trade import Trade2Client

    t = Trade2Client()
    out = {}

    def base_q(cat, rarity=None):
        q = {"query": {"status": {"option": "online"}, "filters": {
            "type_filters": {"filters": {"category": {"option": cat}}},
            "req_filters": {"filters": {"lvl": {"max": char_level}}},
            "trade_filters": {"filters": {"price": {"option": "exalted", "max": price_cap}}}}},
            "sort": {"price": "asc"}}
        if rarity:
            q["query"]["filters"]["type_filters"]["filters"]["rarity"] = {"option": rarity}
        return q

    def run(q, convert):
        try:
            res = t.search(league, q)
            hashes = res.get("result", [])[:per_cat]
            if not hashes:
                return []
            listings = t.fetch(hashes, res["id"])
        except Exception as exc:
            log(f"  harvest failed: {exc}")
            return []
        items = []
        for entry in listings:
            price = entry.get("listing", {}).get("price") or {}
            if price.get("currency") != "exalted":
                continue
            items.append({
                "name": entry["item"].get("name") or entry["item"].get("typeLine", "?"),
                "price": float(price.get("amount", 0)),
                "item_text": convert(entry["item"]),
                "whisper": entry.get("listing", {}).get("whisper"),
                "seller": entry.get("listing", {}).get("account", {}).get("name"),
            })
        return items

    return t, base_q, run


def harvest_all(mcp_path, engine, league, char_level, price_cap, log=print):
    """engine: a Worker (for item conversion via convert_trade_item).

    Returns {type_name: {"items": [...], "medium": item|None, "bis": item|None}}.
    medium = best listing at <=medium price (1ex or budget/5); bis = best listing
    regardless of budget (capped at 60ex to dodge troll listings).
    """
    t, base_q, run = harvest(mcp_path, league, char_level, price_cap, log=log)

    def convert(item_json):
        return engine.call("convert_trade_item", {"item": item_json})["item_string"]

    medium_cap = max(1.0, price_cap / 5)
    out = {}
    for type_name, (cat, martial) in CATEGORIES.items():
        def query_tier(cap, strong):
            q = base_q(cat)
            q["query"]["filters"]["trade_filters"]["filters"]["price"]["max"] = cap
            if martial:
                q["sort"] = {"dps": "desc"}
            else:
                lvl_stat = MINION_LEVELS if type_name == "Sceptre" else SPELL_LEVELS
                q["query"]["stats"] = [{"type": "count", "value": {"min": 1}, "filters": [
                    {"id": lvl_stat, "value": {"min": 3 if strong else 2}},
                    {"id": ALL_LEVELS, "value": {"min": 1}}]}]
            return q

        medium_items = run(query_tier(medium_cap, False), convert)
        time.sleep(1)
        bis_items = run(query_tier(60, True), convert)
        time.sleep(1)
        # uniques compete in both tiers
        qu = base_q(cat, rarity="unique")
        if martial:
            qu["sort"] = {"dps": "desc"}
        uniques = run(qu, convert)
        time.sleep(1)

        pool = medium_items + bis_items + uniques
        seen, items = set(), []
        for it in pool:
            if it["name"] in seen:
                continue
            seen.add(it["name"])
            items.append(it)
        medium = next((i for i in medium_items + [u for u in uniques if u["price"] <= medium_cap]), None)
        bis = next(iter(bis_items), None) or medium
        out[type_name] = {"items": items, "medium": medium, "bis": bis}
        log(f"harvest {type_name}: medium={medium['name'] if medium else None} "
            f"bis={bis['name'] if bis else None} (+{len(items)} pool)")
    return out
