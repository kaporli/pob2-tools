"""Assertion-based replacement for the print-only engine smoke script (P00-T02).

The previous ``pob2-mcp/test_engine.py`` booted PoB at module import, hardcoded
one machine's checkout path on ``sys.path``, printed its results and always
exited 0. It could not fail. This file exercises the same handlers and asserts
on them; the PoB checkout comes from ``POB2_ROOT`` or the bundled submodule.
"""

from __future__ import annotations

import pytest

from engine_helpers import FIXTURE_WEAPON, STRONGER_WEAPON, allocated_count, equipped_count

pytestmark = pytest.mark.engine


def test_new_build_returns_a_summary(blank_build):
    summary = blank_build.call("new_build")
    assert summary["level"] >= 1
    assert isinstance(summary["class"], str) and summary["class"]
    assert summary["passivePointsUsed"] == 0


def test_engine_internals_are_reachable(blank_build):
    probe = blank_build.eval_lua(
        "return { targetVersion = tostring(build.targetVersion), "
        "hasVersionData = build.targetVersionData and 1 or 0, "
        "classes = #build.spec.tree.classes }")

    assert probe["classes"] > 0
    assert probe["targetVersion"] != "nil"
    # Characterized, not required: `build.targetVersionData` is nil on the
    # pinned checkout. The replaced smoke script printed this as `version = 0`
    # and reported success anyway. Resolving what identifies a patch belongs to
    # P02-T02; nothing here may be read as patch evidence.
    assert probe["hasVersionData"] == 0


def test_search_nodes_returns_matching_passives(blank_build):
    nodes = blank_build.call("search_nodes", {"text": "projectile damage", "limit": 5})
    assert nodes, "no passive matched a common search term"
    assert len(nodes) <= 5
    for node in nodes:
        assert isinstance(node["id"], int)
        assert "projectile damage" in (
            node["name"] + "\n" + "\n".join(node.get("stats") or [])).lower()


def test_allocating_a_node_spends_points(blank_build):
    nodes = blank_build.call("search_nodes", {"text": "projectile damage", "limit": 5})
    before = allocated_count(blank_build)
    result = blank_build.call("alloc_nodes", {"ids": [nodes[0]["id"]]})

    assert result["pointsUsed"] > 0
    assert allocated_count(blank_build) > before


def test_allocation_pathing_and_deallocation_are_not_symmetric(blank_build):
    """Characterization, not an approval of the rule (observation P00-OBS-02).

    Allocating one distant passive also allocates every node on the path to it.
    Deallocating that same passive removes only the named node and leaves the
    path allocated, so alloc+dealloc does not return to the starting state.
    Whether orphaned path nodes should be pruned is a game-rule question owned
    by P02-T03; this test only pins what the engine does today.
    """
    nodes = blank_build.call("search_nodes", {"text": "projectile damage", "limit": 5})
    target = nodes[0]["id"]
    baseline = allocated_count(blank_build)

    allocated = blank_build.call("alloc_nodes", {"ids": [target]})
    after_alloc = allocated_count(blank_build)
    assert after_alloc > baseline + 1, "expected path allocation, not a single node"
    assert allocated["pointsUsed"] == after_alloc - baseline

    blank_build.call("dealloc_nodes", {"ids": [target]})
    after_dealloc = allocated_count(blank_build)

    assert after_dealloc == after_alloc - 1
    assert after_dealloc > baseline
    assert not any(n["id"] == target for n in blank_build.call("get_tree")["allocated"])


def test_get_stats_reports_numeric_defences(blank_build):
    stats = blank_build.call("get_stats")
    assert stats["Life"] > 0
    for key in ("TotalDPS", "FullDPS", "CombinedDPS"):
        assert isinstance(stats[key], (int, float))


def test_equipping_a_weapon_changes_damage(blank_build):
    before = blank_build.call("get_stats")["TotalDPS"]
    result = blank_build.call("equip_item", {"raw": FIXTURE_WEAPON, "slot": "Weapon 1"})

    assert "Long Quarterstaff" in result["name"]
    assert equipped_count(blank_build) == 1
    assert blank_build.call("get_stats")["TotalDPS"] > before


def test_test_item_compares_without_equipping(blank_build):
    blank_build.call("equip_item", {"raw": FIXTURE_WEAPON, "slot": "Weapon 1"})
    equipped_before = blank_build.call("get_items")
    stats_before = blank_build.call("get_stats")

    diff = blank_build.call("test_item", {"raw": STRONGER_WEAPON, "slot": "Weapon 1"})

    assert diff["diff"]["TotalDPS"]["delta"] > 0
    # Non-destructive: the equipped item and the live stats are unchanged.
    assert blank_build.call("get_items") == equipped_before
    assert blank_build.call("get_stats")["TotalDPS"] == pytest.approx(stats_before["TotalDPS"])


def test_save_and_load_round_trip_preserves_tree_and_items(blank_build):
    nodes = blank_build.call("search_nodes", {"text": "projectile damage", "limit": 5})
    blank_build.call("alloc_nodes", {"ids": [n["id"] for n in nodes[:2]]})
    blank_build.call("equip_item", {"raw": FIXTURE_WEAPON, "slot": "Weapon 1"})
    expected_nodes = allocated_count(blank_build)
    expected_items = equipped_count(blank_build)

    xml = blank_build.call("save_build_xml")["xml"]
    assert xml.startswith("<?xml")
    blank_build.call("load_build_xml", {"xml": xml, "name": "round-trip"})

    assert allocated_count(blank_build) == expected_nodes
    assert equipped_count(blank_build) == expected_items


def test_convert_trade_item_builds_a_parsable_item_string(blank_build):
    trade_item = {
        "rarity": "Rare",
        "name": "Fixture Knuckle",
        "typeLine": "Long Quarterstaff",
        "ilvl": 81,
        "implicitMods": [],
        "explicitMods": [
            {"description": "Adds 50 to 80 Physical Damage"},
            {"description": "25% increased Attack Speed"},
        ],
    }
    item_string = blank_build.call("convert_trade_item", {"item": trade_item})["item_string"]

    assert item_string.splitlines()[:3] == [
        "Rarity: Rare", "Fixture Knuckle", "Long Quarterstaff"]
    # The converted string is accepted by the item parser it is meant to feed.
    equipped = blank_build.call("equip_item", {"raw": item_string, "slot": "Weapon 1"})
    assert "Fixture Knuckle" in equipped["name"]
