"""P04 and the P02 support follow-up against the pinned engine.

For every PoB-written fixture document:

    PoB XML -> parse (catalog naming) -> BuildSpec v2 -> our XML -> PoB
            -> PoB XML -> BuildSpec v2

and four separate claims are checked:

* PoB evaluates our document exactly as it evaluated the source: the same
  socket group count, main skill, and every numeric output within the
  P02-T01 tolerance;
* the canonical identity survives PoB's own save, support settings and main
  group included;
* a support setting we change is carried through PoB's load and save, and
  the stats notice it, so the comparisons above are not vacuous;
* each variant of the loadout document evaluates as PoB evaluates that
  loadout when the document itself selects it.

The documents are synthetic compositions saved by PoB (``tests/p04_fixtures``);
nothing here is a gameplay measurement.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import replace

import pytest

import p04_fixtures as fx
from pob2opt.domain.identity import build_identity
from pob2opt.evaluation import export_build, import_build
from pob2opt.evaluation.roundtrip import diff_identity
from pob2opt.evaluation.variants import SET_TABLES
from pob2opt.parsers import naming_from_catalog, parse_document
from pob2opt.parsers.resolve import class_for_document_name

pytestmark = pytest.mark.engine

REL_TOLERANCE = 1e-6
ABS_TOLERANCE = 1e-9
ALL_BUILDS = fx.COMPLETE_BUILDS + fx.PARTIAL_BUILDS


@pytest.fixture(scope="module", autouse=True)
def _collect_engine_garbage(engine):
    """The session engine runs every engine module; start this one clean."""
    engine.call("eval", {"code": "collectgarbage('collect')"})
    yield
    engine.call("eval", {"code": "collectgarbage('collect')"})


def _numeric(stats):
    return {k: v for k, v in stats.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)}


def _evaluate(engine, xml):
    summary = engine.call("load_build_xml", {"xml": xml})
    stats = _numeric(engine.call("get_stats", {"all": True}))
    return summary, stats


def _stat_differences(before, after):
    out = {}
    for key, value in before.items():
        other = after.get(key)
        if other is None:
            out[key] = (value, None)
            continue
        delta = abs(float(other) - float(value))
        relative = delta / abs(float(value)) if value else 0.0
        if delta > ABS_TOLERANCE and relative > REL_TOLERANCE:
            out[key] = (value, other)
    return out


def _naming(xml):
    root = ET.fromstring(xml)
    class_id = class_for_document_name(fx.entities(),
                                       root.find("Build").get("className"))
    return naming_from_catalog(fx.entities(), class_id=class_id).naming


def _parse(name):
    data = fx.document_bytes(name)
    return parse_document(fx.source(data, record_id="src/" + name), data,
                          fx.context())


@pytest.fixture(scope="module")
def trips(engine):
    """Every fixture: PoB's evaluation of the source and of our export."""
    out = {}
    for name in ALL_BUILDS:
        source_xml = fx.document_bytes(name).decode("utf-8")
        outcome = _parse(name)
        (build,) = outcome.builds
        items = {item.item_hash: item for item in outcome.items}
        naming = _naming(source_xml)
        exported = export_build(build, items, naming)
        source_summary, source_stats = _evaluate(engine, source_xml)
        our_summary, our_stats = _evaluate(engine, exported.xml)
        resaved = engine.call("save_build_xml")["xml"]
        out[name] = dict(build=build, items=items, naming=naming,
                         exported=exported, resaved=resaved,
                         source_summary=source_summary,
                         source_stats=source_stats, our_summary=our_summary,
                         our_stats=our_stats)
    return out


@pytest.mark.parametrize("name", ALL_BUILDS)
def test_pob_evaluates_our_export_as_it_evaluated_the_source(trips, name):
    trip = trips[name]
    for key in ("class", "ascendancy", "level", "allocatedNodes",
                "equippedItems", "socketGroups", "mainSkill",
                "passivePointsUsed"):
        assert trip["our_summary"][key] == trip["source_summary"][key], key
    assert len(trip["source_stats"]) > 100
    differences = _stat_differences(trip["source_stats"], trip["our_stats"])
    assert differences == {}, differences


@pytest.mark.parametrize("name", ALL_BUILDS)
def test_identity_survives_pobs_own_save(trips, name):
    trip = trips[name]
    second = import_build(trip["resaved"], trip["naming"], record_id="again",
                          created_at=fx.CREATED_AT,
                          catalog_hash=trip["build"].catalog_hash)
    differences = diff_identity(build_identity(trip["build"]),
                                build_identity(second.build))
    assert differences == [], [d.as_dict() for d in differences]


@pytest.mark.parametrize("name", fx.COMPLETE_BUILDS)
def test_a_complete_import_exports_as_the_recommended_deliverable(trips,
                                                                  name):
    trip = trips[name]
    assert trip["build"].parse_status.value == "complete"
    assert trip["exported"].recommended_deliverable, \
        trip["exported"].report.as_dict()


@pytest.mark.parametrize("name", fx.PARTIAL_BUILDS)
def test_a_partial_import_never_exports_as_a_deliverable(trips, name):
    trip = trips[name]
    assert trip["build"].parse_status.value == "partial"
    assert not trip["exported"].recommended_deliverable


def _with_support(build, change):
    """``build`` with the first support of the first skill changed."""
    for gi, group in enumerate(build.skill_groups):
        for si, skill in enumerate(group.skills):
            if skill.support_ids:
                supports = list(skill.supports)
                supports[0] = change(supports[0])
                skills = list(group.skills)
                skills[si] = replace(skill, supports=supports)
                groups = list(build.skill_groups)
                groups[gi] = replace(group, skills=skills)
                return replace(build, skill_groups=groups), supports[0]
    return None, None


@pytest.mark.parametrize("name", fx.COMPLETE_BUILDS)
def test_a_changed_support_state_is_carried_through_pob(engine, trips, name):
    """Our support settings reach PoB and come back from PoB's own save."""
    trip = trips[name]
    changed, support = _with_support(
        trip["build"], lambda s: replace(s, enabled=not s.enabled,
                                         quality=(s.quality or 0) + 1))
    if changed is None:
        pytest.skip("fixture %s has no support" % name)
    exported = export_build(changed, trip["items"], trip["naming"])
    engine.call("load_build_xml", {"xml": exported.xml})
    resaved = engine.call("save_build_xml")["xml"]
    again = import_build(resaved, trip["naming"], record_id="changed",
                         created_at=fx.CREATED_AT,
                         catalog_hash=changed.catalog_hash).build
    _, round_tripped = _with_support(again, lambda s: s)
    assert (round_tripped.enabled, round_tripped.quality) == (
        support.enabled, support.quality)
    assert build_identity(again) == build_identity(changed)


def test_disabling_supports_changes_what_pob_calculates(engine, trips):
    """At least one fixture's outputs move when a support is switched off."""
    moved = []
    for name in fx.COMPLETE_BUILDS:
        trip = trips[name]
        changed, support = _with_support(
            trip["build"], lambda s: replace(s, enabled=not s.enabled))
        if changed is None:
            continue
        _, stats = _evaluate(engine, export_build(
            changed, trip["items"], trip["naming"]).xml)
        if _stat_differences(trip["our_stats"], stats):
            moved.append(name)
    assert moved, "no support state change was visible in any fixture"


# --------------------------------------------------------------- variants

def _selecting(xml, selection):
    """The source document with its own selectors set to one loadout."""
    root = ET.fromstring(xml)
    for tag, _, selector in SET_TABLES:
        if tag in selection and root.find(tag) is not None:
            root.find(tag).set(selector, selection[tag])
    return ET.tostring(root, encoding="unicode")


def test_each_variant_evaluates_as_pob_evaluates_that_loadout(engine):
    source_xml = fx.document_bytes("variants").decode("utf-8")
    outcome = _parse("variants")
    naming = _naming(source_xml)
    items = {item.item_hash: item for item in outcome.items}
    assert len(outcome.split.variants) == 2
    for variant in outcome.split.variants:
        build = next(b for b in outcome.builds
                     if b.variant_id == variant.variant_id)
        _, expected = _evaluate(engine, _selecting(source_xml,
                                                   variant.selection))
        exported = export_build(build, items, naming)
        assert exported.recommended_deliverable, exported.report.as_dict()
        _, ours = _evaluate(engine, exported.xml)
        assert _stat_differences(expected, ours) == {}, variant.label


def test_the_two_loadouts_are_different_builds(engine):
    outcome = _parse("variants")
    first, second = outcome.builds
    assert first.build_hash != second.build_hash
    assert first.raw_blob_hashes == second.raw_blob_hashes
    assert first.source_document_ids == second.source_document_ids
