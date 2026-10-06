"""P02-T05 against the pinned engine: PoB writes, we read, we write, PoB reads.

The offline lane compares our exporter against our importer, which cannot show
that PoB accepts the document. This lane starts from a document PoB itself
wrote and ends with PoB loading ours:

    PoB build -> PoB XML -> BuildSpec A -> our XML -> PoB -> PoB XML -> BuildSpec B

and asserts three separate things:

* PoB loads our document and reports the same tree, gear and socket groups;
* the deterministic primitives of the two loads agree within the P02-T01
  tolerance, so the document did not quietly change the character;
* ``build_identity(A) == build_identity(B)``, compared as canonical semantics.
  PoB assigns its own internal numeric item and node IDs on load, so XML byte
  equality is not the test and would fail on a correct export.

The naming table is derived from the document PoB wrote
(``naming_from_document``). Its right-hand side is PoB's own names; the
catalog IDs on the left are invented by prefixing them, because P02-T02 owns
the real catalog. Nothing here is a gameplay measurement.
"""

from __future__ import annotations

import pytest
from p02_t05_fixtures import naming_from_document

from pob2opt.domain.identity import build_identity
from pob2opt.evaluation import export_build, import_build
from pob2opt.evaluation.roundtrip import diff_identity

pytestmark = pytest.mark.engine

#: P02-T01's acceptance tolerance for deterministic primitives.
REL_TOLERANCE = 1e-6
ABS_TOLERANCE = 1e-9

FIXTURE_WEAPON = "\n".join([
    "Rarity: RARE",
    "FIXTURE P02-T05 Quarterstaff",
    "Long Quarterstaff",
    "Item Level: 80",
    "Quality: 20",
    "LevelReq: 60",
    "Implicits: 0",
    "Adds 60 to 90 Physical Damage",
    "{crafted}Adds 20 to 30 Fire Damage",
])

CREATED_AT = "2026-10-06T00:00:00Z"
CATALOG_HASH = "e" * 64


@pytest.fixture(scope="module")
def pob_document(engine) -> str:
    """A build with a tree, an item and a socket group, saved by PoB itself.

    Built in the session engine rather than a throwaway one. A second
    ``Pob2Engine`` in the same process shares the native state, so closing one
    leaves the session engine unusable for every test after it.
    """
    engine.call("new_build")
    nodes = engine.call("search_nodes", {"text": "projectile damage",
                                         "limit": 5})
    engine.call("alloc_nodes", {"ids": [n["id"] for n in nodes[:2]]})
    engine.call("equip_item", {"raw": FIXTURE_WEAPON, "slot": "Weapon 1"})
    return engine.call("save_build_xml")["xml"]


@pytest.fixture(scope="module")
def naming(pob_document: str):
    return naming_from_document(pob_document)


@pytest.fixture(scope="module")
def first_import(pob_document: str, naming):
    return import_build(pob_document, naming, record_id="p02t05-a",
                        created_at=CREATED_AT, catalog_hash=CATALOG_HASH)


@pytest.fixture(scope="module")
def exported(first_import, naming):
    return export_build(first_import.build, first_import.items, naming)


@pytest.fixture(scope="module")
def reloaded(engine, pob_document: str, exported):
    """Load our document in PoB, then read PoB's own save of it back."""
    original = engine.call("load_build_xml", {"xml": pob_document})
    original_stats = engine.call("get_stats", {"all": True})
    ours = engine.call("load_build_xml", {"xml": exported.xml})
    our_stats = engine.call("get_stats", {"all": True})
    resaved = engine.call("save_build_xml")["xml"]
    return {"original_summary": original, "original_stats": original_stats,
            "our_summary": ours, "our_stats": our_stats, "resaved": resaved}


def test_our_document_loads_in_the_pinned_pob(reloaded):
    """``load_build_xml`` raises on a document PoB cannot read (P00-OBS-01)."""
    assert reloaded["our_summary"]["class"] == reloaded["original_summary"]["class"]
    assert reloaded["our_summary"]["level"] == reloaded["original_summary"]["level"]


def test_the_tree_the_gear_and_the_socket_groups_survive(reloaded):
    for key in ("allocatedNodes", "equippedItems", "socketGroups",
                "passivePointsUsed"):
        assert reloaded["our_summary"][key] == reloaded["original_summary"][key], key


def test_deterministic_primitives_agree_after_the_round_trip(reloaded):
    before = reloaded["original_stats"]
    after = reloaded["our_stats"]
    compared = 0
    worst_abs = 0.0
    worst_rel = 0.0
    for key, value in sorted(before.items()):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        assert key in after, key
        other = after[key]
        assert isinstance(other, (int, float)), key
        delta = abs(float(other) - float(value))
        relative = delta / abs(float(value)) if value else 0.0
        worst_abs = max(worst_abs, delta)
        worst_rel = max(worst_rel, relative)
        compared += 1
        assert delta <= ABS_TOLERANCE or relative <= REL_TOLERANCE, (
            key, value, other)
    assert compared > 100, compared
    assert worst_abs == 0.0 or worst_rel <= REL_TOLERANCE


def test_the_exported_document_keeps_the_fixture_affix(exported):
    assert "Adds 60 to 90 Physical Damage" in exported.xml
    assert "{crafted}Adds 20 to 30 Fire Damage" in exported.xml


def test_canonical_build_identity_survives_a_pob_round_trip(first_import,
                                                            naming, reloaded):
    second = import_build(reloaded["resaved"], naming, record_id="p02t05-b",
                          created_at=CREATED_AT, catalog_hash=CATALOG_HASH)
    differences = diff_identity(build_identity(first_import.build),
                                build_identity(second.build))
    assert differences == [], [d.as_dict() for d in differences]
    assert first_import.build.build_hash == second.build.build_hash


def test_identity_is_not_xml_byte_equality(exported, reloaded):
    """PoB renumbers; the documents differ and the semantics do not."""
    assert exported.xml != reloaded["resaved"]


def test_the_export_of_a_pob_derived_build_is_complete(exported):
    """Nothing in a document PoB wrote is outside what we can write back."""
    assert exported.completeness == "complete", exported.report.as_dict()
    assert exported.recommended_deliverable is True
    for loss in exported.report.unsupported:
        assert loss.reason.strip()
        assert loss.field_path.startswith("/")


def test_the_comparison_would_notice_a_damaged_export(engine, exported,
                                                      reloaded):
    """Otherwise the checks above could pass on an empty document.

    Dropping the item from our export must change what PoB reports, so the
    equality assertions are measuring the document and not the fixture.
    """
    damaged = exported.xml.replace('<Slot name="Weapon 1" itemId="1" />',
                                   '<Slot name="Weapon 1" itemId="0" />')
    assert damaged != exported.xml
    summary = engine.call("load_build_xml", {"xml": damaged})
    assert summary["equippedItems"] == 0
    assert summary["equippedItems"] != reloaded["original_summary"]["equippedItems"]
    stats = engine.call("get_stats", {"all": True})
    assert stats.get("CombinedAvg") != reloaded["original_stats"]["CombinedAvg"]
