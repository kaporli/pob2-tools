"""P02-T04 offline lane: the declared primitive inventory.

No PoB and no network. What the engine actually reports, and whether a
semantic is really included, is settled in ``tests/engine/test_p02_t04_*``
and recorded in ``docs/evidence/P02/primitives.md``. These tests check the
table's own rules: one owner and one unit per primitive, a conditional unit
that stays unresolved until the engine fact that decides it is present, and a
missing native output that becomes a gap instead of a number.
"""

from __future__ import annotations

import dataclasses

import pytest

from pob2opt.evaluation import primitives as prim
from pob2opt.evaluation.protocol import (BuildDocument, DocumentProvenance,
                                         EngineIdentity, LoadedBuild,
                                         PrimitiveSnapshot)

#: The categories P02-T04 was told to inventory.
REQUIRED_CATEGORIES = (
    "damage_per_hit_or_use", "damage_over_time", "attack_or_cast_time",
    "resource_cost", "cooldown", "hit_probability", "target_count", "defences")


# ------------------------------------------------------------- table rules

def test_every_primitive_id_is_unique():
    ids = [d.primitive_id for d in prim.PRIMITIVES]
    assert len(ids) == len(set(ids))


def test_no_native_output_is_claimed_by_two_primitives():
    """One declared owner per primitive, and one primitive per engine key."""
    keys = [d.native_key for d in prim.PRIMITIVES if d.native_key is not None]
    assert len(keys) == len(set(keys))


def test_every_primitive_declares_a_unit_an_owner_and_its_evidence():
    for d in prim.PRIMITIVES:
        assert d.unit, d.primitive_id
        assert d.owner in (prim.OWNER_POB, prim.OWNER_SIMULATOR), d.primitive_id
        assert d.evidence, d.primitive_id
        assert d.status in (prim.STATUS_DECLARED, prim.STATUS_CONDITIONAL,
                            prim.STATUS_GAP), d.primitive_id


def test_a_conditional_primitive_names_what_resolves_it():
    for d in prim.PRIMITIVES:
        if d.status == prim.STATUS_CONDITIONAL:
            assert d.resolved_by, d.primitive_id


def test_a_primitive_with_no_native_key_is_owned_by_the_simulator():
    """PoB supplies no value, so P07 computes it. It is never both."""
    for d in prim.PRIMITIVES:
        if d.native_key is None:
            assert d.owner == prim.OWNER_SIMULATOR, d.primitive_id
            assert d.status == prim.STATUS_GAP, d.primitive_id
        else:
            assert d.owner == prim.OWNER_POB, d.primitive_id


def test_every_inventoried_category_is_covered():
    for category in REQUIRED_CATEGORIES:
        assert category in prim.CATEGORIES
        assert prim.CATEGORIES[category]
        for primitive_id in prim.CATEGORIES[category]:
            assert primitive_id in prim.BY_ID, (category, primitive_id)


def test_every_primitive_belongs_to_exactly_one_category():
    seen: dict[str, str] = {}
    for category, ids in prim.CATEGORIES.items():
        for primitive_id in ids:
            assert primitive_id not in seen, (
                primitive_id, seen.get(primitive_id), category)
            seen[primitive_id] = category
    assert set(seen) == set(prim.BY_ID)


def test_the_definitions_are_immutable():
    definition = prim.BY_ID["damage_per_use"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        definition.unit = "whatever"  # type: ignore[misc]


# ------------------------------------------------------------ declaring values

def test_a_present_output_is_declared_with_its_unit():
    declared, _ = prim.declare({"AverageDamage": 15.88359375})

    assert declared["damage_per_use"].value == 15.88359375
    assert declared["damage_per_use"].unit == "damage per use"
    assert declared["damage_per_use"].definition.owner == prim.OWNER_POB


def test_a_missing_output_is_a_gap_not_a_constant():
    declared, gaps = prim.declare({"AverageDamage": 1.0})

    assert "cooldown_s" not in declared
    gap = next(g for g in gaps if g.primitive_id == "cooldown_s")
    assert gap.kind == "missing_input"
    assert gap.native_key == "Cooldown"
    assert gap.needed_evidence


def test_a_simulator_owned_primitive_is_always_a_gap():
    _, gaps = prim.declare({"AverageDamage": 1.0})

    for primitive_id in ("targets_hit_per_use", "trigger_rate_per_second",
                         "projectile_overlap_multiplier",
                         "sustained_damage_per_second"):
        gap = next(g for g in gaps if g.primitive_id == primitive_id)
        assert gap.kind == "unsupported_rule"
        assert gap.owner == prim.OWNER_SIMULATOR
        assert gap.native_key is None


def test_combined_dps_is_not_declared_until_its_unit_is_known():
    """Guessing costs a factor of the skill's use rate (fixture F-UNIT)."""
    values = {"CombinedDPS": 23.32}

    declared, gaps = prim.declare(values)
    assert "combined_damage" not in declared
    assert any(g.primitive_id == "combined_damage" for g in gaps)

    per_use, _ = prim.declare(values, show_average=True)
    assert per_use["combined_damage"].unit == "damage per use"

    per_second, _ = prim.declare(values, show_average=False)
    assert per_second["combined_damage"].unit == "damage per second"


# ------------------------------------------------------------ on the snapshot

def snapshot(values, *, show_average=None) -> PrimitiveSnapshot:
    document = BuildDocument("fixture-build", "<SyntheticBuild/>")
    loaded = LoadedBuild(name="fixture", class_name=None, ascendancy=None,
                         level=1, allocated_nodes=0, equipped_items=0,
                         socket_groups=0, opt_setup_called=False,
                         main_skill_show_average=show_average)
    return PrimitiveSnapshot(
        build_hash="fixture-build", values=values, stat_keys=tuple(values),
        identity=EngineIdentity(pob_root="", pob_commit=None,
                                pob_dirty_hash=None, adapter_version="test",
                                helper_lua_hashes=(), worker_pid=0,
                                worker_cwd="", generation=1),
        state_applied={}, loaded=loaded,
        document=DocumentProvenance.of(document, reloaded=True),
        timeout_s=1.0, load_timeout_s=None, duration_ms=0)


def test_a_snapshot_declares_the_units_of_what_the_engine_returned():
    snap = snapshot({"TotalDPS": 20.013328125, "Speed": 1.26,
                     "AverageDamage": 15.88359375})

    assert snap.semantics_status == "declared"
    assert snap.semantics_owner == "P02-T04"
    assert snap.semantics_version == prim.SEMANTICS_VERSION
    assert snap.primitive("hit_damage_per_second").unit == "damage per second"
    assert snap.primitive("use_rate_per_second").unit == "uses per second"


def test_a_snapshot_returns_none_for_a_primitive_it_does_not_have():
    snap = snapshot({"TotalDPS": 1.0})

    assert snap.primitive("cooldown_s") is None
    assert snap.primitive("life") is None
    assert any(g.primitive_id == "life" for g in snap.gaps())


def test_a_snapshot_resolves_combined_dps_from_the_engine_flag():
    unresolved = snapshot({"CombinedDPS": 23.32})
    assert unresolved.primitive("combined_damage") is None

    resolved = snapshot({"CombinedDPS": 23.32}, show_average=True)
    assert resolved.primitive("combined_damage").unit == "damage per use"


def test_declared_and_gaps_never_overlap():
    snap = snapshot({"TotalDPS": 1.0, "Life": 65})
    declared = set(snap.declared())
    gapped = {g.primitive_id for g in snap.gaps()}

    assert not declared & gapped
    assert declared | gapped == set(prim.BY_ID)
