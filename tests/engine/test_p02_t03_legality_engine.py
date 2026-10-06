"""P02-T03 against the real PoB engine.

What only the engine can establish:

* `legality_state` reports the allocation, equipment, skills and calculated
  pools the engine actually holds after an exact load, and reports them
  without disturbing a build another request already loaded;
* a document PoB imports without a complaint can still be illegal. The whole
  reason allocation and equipment are verified after the import is that a
  clean import proves the document parsed and nothing else;
* the record is checked against the engine rather than believed: a BuildSpec
  claiming a level and an allocation its own document does not produce is a
  violation, not something to correct;
* connectivity is decided against the real passive tree, which has about five
  thousand nodes and the edges the engine derives from them.

One adapter and one catalog export serve the whole module: both cost real
time. The export runs with an empty compatibility fixture set because the
compatibility verdict is P02-T02's claim and not this module's.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import legality_fixtures as fixtures

from pob2opt.catalog import (EngineCatalogReader, ExportRequest,
                             PobCatalogProvider)
from pob2opt.catalog.sources import read_citations
from pob2opt.domain.enums import Fidelity, Legality
from pob2opt.evaluation import (BuildDocument, EngineAdapter, EngineState,
                                pob_worker_spec, resolve_checkout)
from pob2opt.evaluation.legality import (CHECK_CONNECTIVITY, CHECK_IMPORT,
                                         CHECK_ITEM_REQUIREMENTS,
                                         CHECK_PASSIVE_BUDGET,
                                         CHECK_RESERVATION, CHECK_SLOTS,
                                         LegalityValidator, normalize_id,
                                         read_imported_state)
from pob2opt.evaluation.legality.gaps import (T02_QUEST_PASSIVE_POINTS,
                                              T02_SLOT_CATEGORIES)

pytestmark = pytest.mark.engine

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_BUILD = REPO_ROOT / "docs" / "evidence" / "P02" / \
    "sample-build-ranger-quarterstaff.xml"

START_TIMEOUT_S = 600.0
REQUEST_TIMEOUT_S = 300.0

#: The sample build's own facts, read out of the document rather than typed.
SAMPLE_CLASS_ID = "poe2/classes/2"


@pytest.fixture(scope="module")
def adapter(pob_root: Path):
    live = EngineAdapter(pob_worker_spec(pob_root),
                         screen_timeout_s=REQUEST_TIMEOUT_S,
                         detailed_timeout_s=REQUEST_TIMEOUT_S,
                         start_timeout_s=START_TIMEOUT_S)
    try:
        yield live
    finally:
        live.close()


@pytest.fixture(scope="module")
def live_export(adapter, pob_root: Path):
    checkout = resolve_checkout(pob_root)
    provider = PobCatalogProvider(
        EngineCatalogReader(adapter, timeout_s=REQUEST_TIMEOUT_S),
        citations=read_citations(pob_root),
        pob_commit=checkout.commit, pob_dirty_hash=checkout.dirty_hash,
        fixtures=fixtures.NO_FIXTURES)
    return provider.export(ExportRequest())


@pytest.fixture(scope="module")
def document_xml() -> str:
    return SAMPLE_BUILD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def document_nodes(document_xml: str) -> list[int]:
    match = re.search(r'nodes="([0-9,]*)"', document_xml)
    assert match, "the sample build declares no allocated nodes"
    return [int(value) for value in match.group(1).split(",") if value]


def _document(xml: str, build_hash: str) -> BuildDocument:
    return BuildDocument(build_hash=build_hash, xml=xml)


def _item(live_export, item_hash: str, base: str, **overrides):
    spec = {"catalog_hash": live_export.catalog.catalog_hash,
            "base_id": base, "display_name": "Fixture Stave",
            "requirements": {}, "source_document_id": "source/sample-build",
            **overrides}
    return fixtures.make_item(item_hash, spec)


def _build(live_export, **overrides):
    spec = {"class_id": SAMPLE_CLASS_ID, "level": 29, "allocated": [], **overrides}
    return fixtures.make_build(spec,
                               catalog_hash=live_export.catalog.catalog_hash,
                               build_hash=overrides.pop("build_hash",
                                                        "p02t03/sample"))


# ------------------------------------------------- what the engine reports ---

def test_the_engine_reports_the_state_it_holds_after_an_exact_load(
        adapter, live_export, document_xml, document_nodes):
    build = _build(live_export, allocated=document_nodes)
    state = read_imported_state(
        adapter, build, live_export.profile,
        document=_document(document_xml, build.build_hash),
        timeout_s=REQUEST_TIMEOUT_S)

    assert state.class_name == "Ranger"
    assert state.class_id == 2
    assert state.level == 29
    assert set(state.allocated_nodes) == set(document_nodes)
    assert state.points_used == len(document_nodes) - 1, (
        "the class start node is allocated and costs no point")
    assert state.class_start_node in document_nodes
    assert not state.unreadable_node_keys

    assert set(state.items) == {"Weapon 1"}
    weapon = state.items["Weapon 1"]
    assert weapon.base_name == "Long Quarterstaff"
    assert weapon.slot_id == "poe2/slots/Weapon 1"
    assert weapon.weapon_set == 1

    assert state.calculated
    assert state.measured.attribute("dexterity") is not None
    spirit = state.measured.pool("spirit")
    assert spirit is not None and spirit.total is not None


def test_a_legality_read_does_not_disturb_a_loaded_build(
        adapter, live_export, document_xml, document_nodes):
    build = _build(live_export, allocated=document_nodes)
    document = _document(document_xml, build.build_hash)
    before = adapter.primitives(build, EngineState(), live_export.profile,
                                fidelity=Fidelity.DETAILED, document=document)
    read_imported_state(adapter, build, live_export.profile, document=document,
                        timeout_s=REQUEST_TIMEOUT_S)
    after = adapter.primitives(build, EngineState(), live_export.profile,
                               fidelity=Fidelity.DETAILED, document=document)
    assert after.document.reloaded is False
    assert after.loaded == before.loaded
    assert after.values == before.values


# ---------------------------------- a clean import is not a legal build ---

def test_a_document_pob_imports_cleanly_can_still_be_illegal(
        adapter, live_export, document_xml, document_nodes):
    """The same build wearing a base that requires level 79, at level 29.

    PoB loads it without a prompt and calculates it happily. Nothing in the
    engine refuses it, which is the point: the import is evidence that the
    document parsed.
    """
    xml = document_xml.replace("Long Quarterstaff", "Aegis Quarterstaff")
    # Drop the item's own LevelReq line so the base's requirement applies.
    xml = xml.replace("LevelReq: 0\n", "")
    assert "Aegis Quarterstaff" in xml and "LevelReq" not in xml
    build = _build(live_export, allocated=document_nodes,
                   equipment={"Weapon 1": {"item": "overreaching-stave"}},
                   build_hash="p02t03/over-level")
    document = _document(xml, build.build_hash)

    loaded = adapter.load_exact_build(document, timeout_s=REQUEST_TIMEOUT_S)
    assert loaded.equipped_items == 1, "PoB accepted the document"
    assert loaded.allocated_nodes == len(document_nodes)

    state = read_imported_state(adapter, build, live_export.profile,
                                document=document, timeout_s=REQUEST_TIMEOUT_S)
    assert state.items["Weapon 1"].base_name == "Aegis Quarterstaff"
    assert state.items["Weapon 1"].requirements.get("level") == 79

    item = _item(live_export, "overreaching-stave", "Aegis Quarterstaff",
                 display_name="Over-reaching Stave")
    report = LegalityValidator(catalog=live_export.catalog,
                               items={item.item_hash: item},
                               imported=state).validate(build,
                                                        live_export.profile)
    assert report.legality is Legality.ILLEGAL
    assert "item_level_requirement_not_met" in report.violation_codes
    assert report.decision(CHECK_ITEM_REQUIREMENTS) is Legality.ILLEGAL
    assert report.decision(CHECK_IMPORT) is Legality.LEGAL, (
        "the record and the engine agree; the item is what is illegal")


def test_the_record_is_verified_against_the_engine_not_believed(
        adapter, live_export, document_xml, document_nodes):
    """A record whose claims its own document does not produce."""
    build = _build(live_export, level=95, allocated=document_nodes[:3],
                   build_hash="p02t03/lying-record")
    state = read_imported_state(
        adapter, build, live_export.profile,
        document=_document(document_xml, build.build_hash),
        timeout_s=REQUEST_TIMEOUT_S)
    report = LegalityValidator(catalog=live_export.catalog,
                               imported=state).validate(build,
                                                        live_export.profile)
    assert report.decision(CHECK_IMPORT) is Legality.ILLEGAL
    assert "import_level_mismatch" in report.violation_codes
    assert "import_allocation_mismatch" in report.violation_codes
    assert report.legality is Legality.ILLEGAL
    # The record is not corrected: the engine's level is what was checked and
    # the record still says 95.
    assert build.level == 95
    level = next(c for c in report.constraints if c.name == "character_level")
    assert level.used == 29


def test_the_faithful_record_agrees_with_the_engine(
        adapter, live_export, document_xml, document_nodes):
    item = _item(live_export, "sample-stave", "Long Quarterstaff")
    build = _build(live_export, allocated=document_nodes,
                   equipment={"Weapon 1": {"item": item.item_hash}},
                   build_hash="p02t03/faithful")
    state = read_imported_state(
        adapter, build, live_export.profile,
        document=_document(document_xml, build.build_hash),
        timeout_s=REQUEST_TIMEOUT_S)
    report = LegalityValidator(catalog=live_export.catalog,
                               items={item.item_hash: item},
                               imported=state).validate(build,
                                                        live_export.profile)
    assert report.violations == (), [f.message for f in report.violations]
    assert report.decision(CHECK_IMPORT) is Legality.LEGAL
    assert report.decision(CHECK_CONNECTIVITY) is Legality.LEGAL
    assert report.decision(CHECK_RESERVATION) is Legality.LEGAL
    # Two things stay undecidable on this profile, and both say why. The
    # build spends 36 points at level 29, which is more than levelling
    # grants and less than a real character's budget; the quest reward
    # total is the gap. Equipment legality has no slot categories at all.
    assert report.decision(CHECK_PASSIVE_BUDGET) is Legality.UNKNOWN
    assert "passive_points_above_levelling_budget" in report.unknown_codes
    assert T02_QUEST_PASSIVE_POINTS in report.cited_gap_ids
    assert report.decision(CHECK_SLOTS) is Legality.UNKNOWN
    assert T02_SLOT_CATEGORIES in report.cited_gap_ids
    assert report.legality is Legality.UNKNOWN


# ------------------------------------------- the real tree, not a fixture ---

def test_a_disconnected_allocation_in_the_real_tree_is_illegal(
        live_export, document_nodes):
    """Remove one node the others reach the start through.

    The cut node is found from the exported edges, not named here, so this
    stays true if the sample build changes.
    """
    index = LegalityValidator(catalog=live_export.catalog).catalog
    allocated = [normalize_id("passive_nodes", node) for node in document_nodes]
    start = index.class_start_node(SAMPLE_CLASS_ID)
    assert start is not None

    def reaches_all(nodes):
        permitted = set(nodes) | {start}
        seen, queue = {start}, [start]
        while queue:
            current = queue.pop()
            for neighbour in index.adjacency.get(current, ()):
                if neighbour in permitted and neighbour not in seen:
                    seen.add(neighbour)
                    queue.append(neighbour)
        return all(node in seen for node in nodes)

    assert reaches_all(allocated), "the sample build is connected to begin with"
    cut = None
    for candidate in allocated:
        if candidate == start:
            continue
        rest = [node for node in allocated if node != candidate]
        if not reaches_all(rest):
            cut = candidate
            break
    assert cut is not None, "no single node strands another in this allocation"

    build = fixtures.make_build(
        {"class_id": SAMPLE_CLASS_ID, "level": 29,
         "allocated": [int(node.rsplit("/", 1)[1]) for node in allocated
                       if node != cut]},
        catalog_hash=live_export.catalog.catalog_hash,
        build_hash="p02t03/cut-tree")
    report = LegalityValidator(catalog=live_export.catalog).validate(
        build, live_export.profile)
    assert report.decision(CHECK_CONNECTIVITY) is Legality.ILLEGAL
    assert "disconnected_passive_allocation" in report.violation_codes


def test_the_live_profile_still_carries_no_slot_categories(live_export):
    rules = live_export.profile.character_rules
    assert rules.slots
    assert all(not rule.accepted_base_categories for rule in rules.slots)
    assert T02_SLOT_CATEGORIES in rules.missing_rule_gap_ids
