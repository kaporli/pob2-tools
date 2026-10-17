"""P04-T05: deduplication, families and the field audit. Offline.

The audit covers the ten complete PoB-written builds and every partial or
ambiguous fixture: the two partial builds, both variants of the loadout
document and the ambiguous-loadout case, plus documents with sections
removed. Every audited gameplay field must match the source, or the record
must declare it unresolved.
"""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from dataclasses import replace

import pytest

import p04_fixtures as fx
from pob2opt.parsers import (CorpusEntry, audit_summary, audit_variant,
                             exact_duplicates, holdout_split,
                             independent_builds, naming_from_catalog,
                             parse_document, propose_family, review_family,
                             with_family)
from pob2opt.parsers.resolve import class_for_document_name

REVIEWED_AT = "2026-10-14T00:00:00Z"


def parsed(name, payload=None, **source):
    data = payload if payload is not None else fx.document_bytes(name)
    document = fx.source(data, record_id=source.pop("record_id", "src/" + name),
                         **source)
    return document, data, parse_document(document, data, fx.context())


def naming_for(data):
    root = ET.fromstring(data)
    class_id = class_for_document_name(fx.entities(),
                                       root.find("Build").get("className"))
    return naming_from_catalog(fx.entities(), class_id=class_id).naming


def audits(data, outcome):
    items = {i.item_hash: i for i in outcome.items}
    naming = naming_for(data)
    out = []
    for variant in outcome.split.variants:
        build = next(b for b in outcome.builds
                     if b.variant_id == variant.variant_id)
        out.append(audit_variant(data.decode("utf-8"), variant.selection,
                                 build, items, naming))
    return out


def ambiguous_variants():
    root = ET.fromstring(fx.document_bytes("variants"))
    items = root.find("Items")
    twin = copy.deepcopy(items.find("ItemSet[@id='2']"))
    twin.set("id", "4")
    items.append(twin)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def without(name, section):
    root = ET.fromstring(fx.document_bytes(name))
    root.remove(root.find(section))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


# ----------------------------------------------------------------- audit ---

def test_ten_complete_variants_match_their_sources_exactly():
    results = []
    for name in fx.COMPLETE_BUILDS:
        _, data, outcome = parsed(name)
        results.extend(audits(data, outcome))
    assert len(results) == 10
    summary = audit_summary(results)
    assert summary["passed"] == 10
    assert summary["undeclared_mismatches"] == []
    for domain in ("allocations", "gear_rolls", "skills_and_supports",
                   "set_bindings"):
        stats = summary["agreement"][domain]
        assert stats["compared"] > 0, domain
        assert stats["exact"] == 1.0, (domain, stats)


PARTIAL_CASES = {
    **{name: lambda name=name: fx.document_bytes(name)
       for name in fx.PARTIAL_BUILDS},
    "variants": lambda: fx.document_bytes("variants"),
    "ambiguous-loadouts": ambiguous_variants,
    "no-items": lambda: without("b04", "Items"),
    "no-tree": lambda: without("b05", "Tree"),
    "no-skills": lambda: without("b08", "Skills"),
}


@pytest.mark.parametrize("case", sorted(PARTIAL_CASES))
def test_partial_and_ambiguous_fixtures_declare_every_difference(case):
    data = PARTIAL_CASES[case]()
    _, _, outcome = parsed(case, data)
    assert outcome.builds
    for result in audits(data, outcome):
        assert result.passed, result.as_dict()


def test_a_wrong_support_setting_fails_the_audit():
    _, data, outcome = parsed("b04")
    (build,) = outcome.builds
    group = build.skill_groups[0]
    skill = group.skills[0]
    wrong = [replace(skill.supports[0], quality=skill.supports[0].quality + 1)]
    wrong += list(skill.supports[1:])
    broken = replace(build, skill_groups=[replace(group, skills=[
        replace(skill, supports=wrong)])] + build.skill_groups[1:])
    variant = outcome.split.variants[0]
    result = audit_variant(data.decode("utf-8"), variant.selection, broken,
                           {i.item_hash: i for i in outcome.items},
                           naming_for(data))
    assert not result.passed
    (mismatch,) = result.mismatches
    assert mismatch.domain == "skills_and_supports"


def test_a_dropped_modifier_line_fails_the_audit():
    _, data, outcome = parsed("b01")
    (build,) = outcome.builds
    items = {i.item_hash: i for i in outcome.items}
    weapon = build.equipment[next(s for s in build.equipment
                                  if build.equipment[s] is not None)]
    item = items[weapon.item_hash]
    items[weapon.item_hash] = replace(item, modifiers=list(item.modifiers[:-1]))
    variant = outcome.split.variants[0]
    result = audit_variant(data.decode("utf-8"), variant.selection, build,
                           items, naming_for(data))
    assert not result.passed
    assert {m.domain for m in result.mismatches} == {"gear_rolls"}


# ------------------------------------------------------------ duplicates ---

def entry(name, record_id, author):
    document, _, outcome = parsed(name, record_id=record_id, author_id=author)
    (build,) = outcome.builds
    return CorpusEntry(build=build, sources=(document,))


def test_identical_copies_group_and_keep_every_creator():
    a = entry("b01", "src/alice", "alice")
    b = entry("b01", "src/bob", "bob")
    c = entry("b03", "src/carol", "carol")
    groups = exact_duplicates([a, b, c])
    by_hash = {g.build_hash: g for g in groups}
    group = by_hash[a.build.build_hash]
    assert group.creators == ("alice", "bob")
    assert group.source_document_ids == ("src/alice", "src/bob")
    assert len(group.record_ids) == 2


def test_identical_copies_are_not_independent_evidence():
    entries = [entry("b01", "src/%d" % i, "creator-%d" % i) for i in range(3)]
    entries.append(entry("b03", "src/other", "other"))
    assert independent_builds(entries) == 2


# --------------------------------------------------------------- families ---

def test_a_family_is_proposed_from_the_main_skill_and_its_interactions():
    _, _, outcome = parsed("b04")
    (build,) = outcome.builds
    proposal = propose_family(build)
    main = build.skill_groups[build.main_skill_group].skills[0]
    assert proposal.mechanism == main.skill_id
    assert set(proposal.interactions) == set(main.support_ids)
    assert proposal.status == "proposed"


def test_only_an_accepted_review_assigns_a_family():
    _, _, outcome = parsed("b04")
    (build,) = outcome.builds
    proposal = propose_family(build)
    rejected = review_family(proposal, accepted=False, reviewer="reviewer",
                             reviewed_at=REVIEWED_AT)
    assert rejected.family_id is None
    with pytest.raises(ValueError):
        with_family(build, rejected, record_id="f", created_at=REVIEWED_AT)
    accepted = review_family(proposal, accepted=True, reviewer="reviewer",
                             reviewed_at=REVIEWED_AT, label="SYNTHETIC family")
    assigned = with_family(build, accepted, record_id="f",
                           created_at=REVIEWED_AT)
    assert assigned.family_id == accepted.family_id
    assert assigned.build_hash == build.build_hash  # identity excludes family
    assert build.family_id is None
    with pytest.raises(ValueError):
        review_family(proposal, accepted=True, reviewer=" ",
                      reviewed_at=REVIEWED_AT)


def test_variants_of_one_family_keep_their_own_records():
    _, _, outcome = parsed("variants")
    first, second = outcome.builds
    label = review_family(propose_family(first), accepted=True,
                          reviewer="reviewer", reviewed_at=REVIEWED_AT,
                          label="SYNTHETIC family")
    one = with_family(first, label, record_id="f1", created_at=REVIEWED_AT)
    other_label = replace(label, proposal=replace(
        label.proposal, build_hash=second.build_hash))
    two = with_family(second, other_label, record_id="f2",
                      created_at=REVIEWED_AT)
    assert one.family_id == two.family_id
    assert one.variant_id != two.variant_id
    assert one.build_hash != two.build_hash


def test_a_holdout_split_never_divides_a_family():
    families = ["family/%d" % i for i in range(40)]
    split = holdout_split(families * 3, seed="s", holdout_fraction=0.25)
    assert set(split) == set(families)
    assert set(split.values()) == {"holdout", "calibration"}
    assert split == holdout_split(families, seed="s", holdout_fraction=0.25)
