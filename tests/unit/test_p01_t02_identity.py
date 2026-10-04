"""Canonical identity (P01-T02).

What must not change a build's combat identity: key order, a display name, a
listing price, a line ending in metadata. What must: a support gem, a passive
choice, an item roll, a progression flag, a weapon-set binding.

Raw documents are the exception. Their hash is over the bytes, so two payloads
differing only in line endings are two different documents, because a byte
difference in a source is evidence.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from record_fixtures import valid_payloads

from pob2opt.domain import (
    ABSENT,
    RECORD_TYPES,
    build_hash,
    build_identity,
    canonical_json,
    canonical_text,
    content_hash,
    document_hash,
    from_jsonable,
    item_hash,
    listing_snapshot_hash,
    rotation_hash,
    scenario_hash,
    to_jsonable,
)
from pob2opt.domain.enums import ConfigOrigin
from pob2opt.domain.identity import baseline_suite_hash
from pob2opt.domain.records import ConfigValue, EquipmentSlot

PAYLOADS = valid_payloads()


def record(kind: str):
    return from_jsonable(RECORD_TYPES[kind], PAYLOADS[kind])


@pytest.fixture
def build():
    return record("build_spec")


@pytest.fixture
def item():
    return record("item_instance")


@pytest.fixture
def listing():
    return record("listing")


# ------------------------------------------------------------ canonical form

def test_canonical_json_sorts_keys_and_stays_compact():
    assert canonical_text({"b": 1, "a": [2, 3]}) == '{"a":[2,3],"b":1}'
    assert canonical_json({"a": 1}) == b'{"a":1}'


def test_canonical_json_is_utf8_without_escapes():
    assert canonical_json({"name": "Ascendancy é"}) == \
        '{"name":"Ascendancy é"}'.encode("utf-8")


def test_canonical_json_refuses_nan_and_infinity():
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            canonical_json({"value": bad})


def test_key_order_does_not_change_a_hash():
    forward = {"a": 1, "b": {"c": 2, "d": 3}}
    reversed_ = {"b": {"d": 3, "c": 2}, "a": 1}
    assert content_hash(forward) == content_hash(reversed_)


# ----------------------------------------------------------- build identity

def test_reordered_json_keys_keep_build_identity(build):
    payload = PAYLOADS["build_spec"]
    shuffled = json.loads(json.dumps(payload, sort_keys=True))
    assert build_hash(from_jsonable(RECORD_TYPES["build_spec"], shuffled)) == \
        build_hash(build)


def test_display_name_changes_keep_build_identity(build):
    assert build_hash(replace(build, name="Something Else")) == build_hash(build)


def test_variant_family_and_provenance_do_not_change_build_identity(build):
    same = replace(build, variant_id="fixture-variant-2",
                   family_id="fixture-family-1",
                   source_document_ids=["fixture-source-2"],
                   declared_patch="fixture-patch-9",
                   created_at="2030-01-01T00:00:00Z")
    assert build_hash(same) == build_hash(build)


def test_import_order_of_passives_does_not_change_identity(build):
    reordered = replace(build, passives=replace(
        build.passives, allocated=list(reversed(build.passives.allocated))))
    assert build_hash(reordered) == build_hash(build)
    assert build_identity(reordered)["passives"]["allocated"] == \
        sorted(build.passives.allocated)


def test_changed_support_changes_identity(build):
    group = build.skill_groups[0]
    skill = replace(group.skills[0], support_ids=["fixture-support-2"])
    changed = replace(build, skill_groups=[replace(group, skills=[skill])])
    assert build_hash(changed) != build_hash(build)


def test_support_order_is_preserved_and_matters(build):
    group = build.skill_groups[0]
    two = replace(group.skills[0], support_ids=["fixture-a", "fixture-b"])
    flipped = replace(group.skills[0], support_ids=["fixture-b", "fixture-a"])
    a = replace(build, skill_groups=[replace(group, skills=[two])])
    b = replace(build, skill_groups=[replace(group, skills=[flipped])])
    assert build_hash(a) != build_hash(b)


def test_changed_passive_choice_changes_identity(build):
    changed = replace(build, passives=replace(
        build.passives, choices={"fixture-node-2": "fixture-choice-str"}))
    assert build_hash(changed) != build_hash(build)


def test_changed_item_roll_changes_identity(build, item):
    modifier = item.modifiers[0]
    rolled = replace(item, modifiers=[replace(
        modifier, values=[replace(modifier.values[0], rolled=11.0)])])
    assert item_hash(rolled) != item_hash(item)
    changed = replace(build, equipment=dict(
        build.equipment,
        **{"fixture-slot-weapon": EquipmentSlot(item_hash=item_hash(rolled),
                                                listing_id="fixture-listing-1")}))
    assert build_hash(changed) != build_hash(build)


def test_changed_progression_flag_changes_identity(build):
    changed = replace(build, progression=replace(
        build.progression, quest_flags={"fixture-quest-1": False}))
    assert build_hash(changed) != build_hash(build)


def test_changed_set_binding_changes_identity(build):
    group = build.skill_groups[0]
    changed = replace(build, skill_groups=[
        replace(group, weapon_set_id="fixture-set-2")])
    assert build_hash(changed) != build_hash(build)


def test_changed_weapon_set_hands_change_identity(build):
    weapon_set = build.weapon_sets[0]
    changed = replace(build, weapon_sets=[replace(
        weapon_set, hand_slots={"main_hand": "fixture-slot-weapon",
                                "off_hand": "fixture-slot-quiver"})])
    assert build_hash(changed) != build_hash(build)


def test_config_value_changes_identity_but_its_origin_does_not(build):
    key = "fixture_condition"
    original = build.config[key]
    relabelled = replace(build, config={key: replace(
        original, origin=ConfigOrigin.MANUAL, verified=True,
        evidence_ids=["fixture-evidence-1"])})
    assert build_hash(relabelled) == build_hash(build)

    flipped = replace(build, config={key: ConfigValue(
        value=False, origin=original.origin, verified=original.verified,
        evidence_ids=original.evidence_ids)})
    assert build_hash(flipped) != build_hash(build)


def test_rotation_ids_are_not_part_of_build_identity(build):
    """Rotation identity is separate, and enters evaluation identity there."""
    assert build_hash(replace(build, rotation_ids=[])) == build_hash(build)
    assert "rotation_ids" not in build_identity(build)


# --------------------------------------------------------- item and listing

def test_display_name_and_raw_text_do_not_change_item_identity(item):
    same = replace(item, display_name="Another Name",
                   raw_text="SYNTHETIC different text",
                   source_document_id="fixture-source-2")
    assert item_hash(same) == item_hash(item)


def test_two_listings_of_the_same_item_share_item_identity(listing, item):
    """Acceptance example 5: equal stats, different price, same item."""
    expensive = replace(listing, record_id="fixture-listing-2",
                        listing_id="fixture-listing-2",
                        price_amount="1000", price_currency="fixture-divine")
    assert expensive.item_hash == listing.item_hash
    assert listing_snapshot_hash(expensive) != listing_snapshot_hash(listing)


def test_an_unknown_price_is_not_a_zero_price(listing):
    unknown = replace(listing, price_amount=None, price_currency=None)
    free = replace(listing, price_amount="0")
    assert listing_snapshot_hash(unknown) != listing_snapshot_hash(free)


def test_listing_price_does_not_reach_build_identity(build):
    """Acceptance example 8: changing only the price is a combat cache hit."""
    slot = build.equipment["fixture-slot-weapon"]
    rebought = replace(build, equipment=dict(
        build.equipment,
        **{"fixture-slot-weapon": replace(slot, listing_id="fixture-listing-2")}))
    assert build_hash(rebought) == build_hash(build)


def test_modifier_category_is_part_of_item_identity(item):
    from pob2opt.domain.enums import ModifierCategory

    recategorized = replace(item, modifiers=[
        replace(item.modifiers[0], category=ModifierCategory.CRAFTED)])
    assert item_hash(recategorized) != item_hash(item)


# -------------------------------------------------- rotations and scenarios

def test_rotation_rule_order_is_identity(repo_root):
    rotation = record("rotation_policy")
    rule = rotation.rules[0]
    second = replace(rule, rule_index=1, action_id="fixture-action-2")
    forward = replace(rotation, rules=[rule, second])
    backward = replace(rotation, rules=[replace(second, rule_index=0),
                                        replace(rule, rule_index=1)])
    assert rotation_hash(forward) != rotation_hash(backward)


def test_rotation_name_and_version_are_labels(repo_root):
    rotation = record("rotation_policy")
    assert rotation_hash(replace(rotation, name="other", version="7")) == \
        rotation_hash(rotation)


def test_scenario_reference_is_not_part_of_scenario_identity():
    """A new reference starts a new leaderboard, not new evaluations."""
    scenario = record("scenario_spec")
    rebased = replace(scenario, reference_build_id="fixture-build-1",
                      reference_result_id="fixture-evaluation-1")
    assert scenario_hash(rebased) == scenario_hash(scenario)
    assert baseline_suite_hash([rebased]) != baseline_suite_hash([scenario])


def test_scenario_version_is_part_of_scenario_identity():
    scenario = record("scenario_spec")
    assert scenario_hash(replace(scenario, version="2")) != \
        scenario_hash(scenario)


# --------------------------------------------------- bytes and line endings

def test_document_hash_preserves_byte_differences():
    unix = b"<Build>\n  <Skills/>\n</Build>\n"
    windows = unix.replace(b"\n", b"\r\n")
    assert document_hash(unix) != document_hash(windows)
    assert document_hash(unix) == document_hash(bytes(unix))


def test_document_hash_refuses_text():
    with pytest.raises(TypeError, match="raw bytes"):
        document_hash("<Build/>")  # type: ignore[arg-type]


def test_newlines_in_metadata_survive_a_round_trip_unchanged(build):
    crlf = replace(build, name="Line one\r\nLine two")
    payload = to_jsonable(crlf)
    again = from_jsonable(RECORD_TYPES["build_spec"], payload)
    assert again.name == "Line one\r\nLine two"
    assert to_jsonable(again) == payload
    assert canonical_json(to_jsonable(again)) == canonical_json(payload)


def test_metadata_newline_style_does_not_change_build_identity(build):
    lf = replace(build, name="Line one\nLine two")
    crlf = replace(build, name="Line one\r\nLine two")
    assert build_hash(lf) == build_hash(crlf) == build_hash(build)


def test_gameplay_text_newlines_do_change_item_identity(item):
    """Modifier text is gameplay data, not metadata; it is hashed verbatim."""
    altered = replace(item, modifiers=[
        replace(item.modifiers[0],
                text=item.modifiers[0].text.replace(" ", "\r\n"))])
    assert item_hash(altered) != item_hash(item)


# --------------------------------------------------------------- stability

def test_hashes_are_stable_across_calls_and_processes(build, item):
    assert build_hash(build) == build_hash(build)
    assert item_hash(item) == item_hash(item)
    assert build.build_hash == build_hash(build), (
        "the fixture records a stale build_hash; the identity projection "
        "changed and the fixture must be updated with it")
    assert item.item_hash == item_hash(item), (
        "the fixture records a stale item_hash")


def test_absent_predicate_members_never_reach_a_hash():
    rotation = record("rotation_policy")
    comparison = rotation.rules[0].predicate.operands[0]
    assert comparison.operands is ABSENT
    assert "operands" not in json.loads(
        canonical_json(to_jsonable(comparison)).decode())
