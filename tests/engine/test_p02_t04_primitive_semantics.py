"""P02-T04 against the real engine: what each primitive actually contains.

Every fixture is a complete build document differing from its pair in one
declared way, built by ``scripts/p02_t04_primitive_fixtures.py`` and read
through the P02-T01 adapter. A field name settles nothing, so each test states
the comparison it rests on; the recorded numbers are in
``docs/evidence/P02/primitives.json`` and the prose inventory is in
``docs/evidence/P02/primitives.md``.

This is engine agreement, not practical accuracy. Nothing here is gameplay
evidence.
"""

from __future__ import annotations

import dataclasses

import pytest

from p02_t04_primitive_fixtures import (META_GEMS, build_fixture_documents,
                                        wrapped_name)
from record_fixtures import records

from pob2opt.domain.enums import Fidelity
from pob2opt.evaluation import (BuildDocument, EngineAdapter, EngineState,
                                pob_worker_spec, resolve_checkout)

pytestmark = pytest.mark.engine

BUILD_HASH = "p02t04-primitive-fixture"
START_TIMEOUT_S = 900.0
REQUEST_TIMEOUT_S = 600.0


@pytest.fixture(scope="module")
def documents(pob_root) -> dict[str, str]:
    """Every fixture document, built in a throwaway engine that then closes."""
    return build_fixture_documents(pob_root)


@pytest.fixture(scope="module")
def adapter(pob_root):
    live = EngineAdapter(pob_worker_spec(pob_root),
                         screen_timeout_s=REQUEST_TIMEOUT_S,
                         detailed_timeout_s=REQUEST_TIMEOUT_S,
                         start_timeout_s=START_TIMEOUT_S)
    try:
        yield live
    finally:
        live.close()


@pytest.fixture(scope="module")
def build_and_profile(pob_root):
    checkout = resolve_checkout(pob_root)
    build = dataclasses.replace(records()["build_spec"], build_hash=BUILD_HASH)
    profile = dataclasses.replace(records()["patch_profile"],
                                  pob_commit=checkout.commit)
    return build, profile


@pytest.fixture(scope="module")
def snapshots(adapter, documents, build_and_profile):
    """One snapshot per fixture, read once for the whole module."""
    build, profile = build_and_profile
    out = {}
    for name, xml in documents.items():
        out[name] = adapter.primitives(build, EngineState(), profile,
                                       document=BuildDocument(BUILD_HASH, xml),
                                       fidelity=Fidelity.DETAILED)
    return out


def declared(snapshot, primitive_id):
    value = snapshot.primitive(primitive_id)
    assert value is not None, primitive_id
    return value


# ------------------------------------------------------ damage per use and DPS

def test_hit_dps_is_damage_per_use_times_the_use_rate(snapshots):
    """F-DPS. The two damage primitives are consistent and separately named."""
    snap = snapshots["baseline"]
    per_use = declared(snap, "damage_per_use")
    rate = declared(snap, "use_rate_per_second")
    per_second = declared(snap, "hit_damage_per_second")

    assert per_use.unit == "damage per use"
    assert rate.unit == "uses per second"
    assert per_second.unit == "damage per second"
    assert per_second.value == pytest.approx(per_use.value * rate.value,
                                             rel=1e-9)


def test_damage_per_use_already_contains_hit_probability_and_crit(snapshots):
    """F-ACC. Multiplying by HitChance downstream would count it twice.

    Accuracy is the only difference between the two documents. Hit chance goes
    25 to 100 and the effective crit chance follows it, because PoB reports
    crit after the hit roll; the damage moves by the product of both, not by
    the hit chance alone.
    """
    base = snapshots["baseline"]
    accurate = snapshots["accuracy"]

    hit_before = declared(base, "hit_probability_pct").value
    hit_after = declared(accurate, "hit_probability_pct").value
    crit_before = declared(base, "crit_chance_pct").value
    crit_after = declared(accurate, "crit_chance_pct").value
    damage_before = declared(base, "damage_per_use").value
    damage_after = declared(accurate, "damage_per_use").value

    assert hit_after > hit_before
    assert damage_after > damage_before
    assert crit_after == pytest.approx(crit_before * hit_after / hit_before,
                                       rel=1e-6)
    # Hit chance alone would predict a 4x move; the measured one is larger
    # because the crit chance it gates moved too.
    assert damage_after / damage_before > hit_after / hit_before


# ---------------------------------------------------------- projectile overlap

def test_extra_projectiles_do_not_multiply_single_target_damage(snapshots):
    """F-PROJ. Projectile overlap is not included, so P07 owns it.

    The only difference is a weapon modifier granting two more arrows. The
    projectile count triples; the damage numbers are bit-identical.
    """
    base = snapshots["baseline"]
    many = snapshots["projectiles"]

    assert declared(base, "projectiles_per_use").value == 1
    assert declared(many, "projectiles_per_use").value == 3
    assert (declared(many, "damage_per_use").value
            == declared(base, "damage_per_use").value)
    assert (declared(many, "hit_damage_per_second").value
            == declared(base, "hit_damage_per_second").value)

    gaps = {g.primitive_id for g in many.gaps()}
    assert "projectile_overlap_multiplier" in gaps
    assert "targets_hit_per_use" in gaps


# ------------------------------------------------------------------- duration

def test_damage_over_time_is_a_rate_that_duration_does_not_change(snapshots):
    """F-DOT. The only difference is a duration support on the same skill."""
    short = snapshots["dot"]
    long = snapshots["dot_longer"]

    assert (declared(long, "skill_effect_duration_s").value
            > declared(short, "skill_effect_duration_s").value)
    assert (declared(long, "dot_damage_per_second").value
            == pytest.approx(declared(short, "dot_damage_per_second").value))
    assert (declared(long, "dot_instance_damage_per_second").value
            == pytest.approx(declared(short, "dot_instance_damage_per_second").value))
    assert declared(short, "dot_damage_per_second").unit == (
        "damage per second while the effect is active")
    # Nothing charges for reapplying the effect, so that cost is P07's.
    assert "dot_reapplication_cost_s" in {g.primitive_id for g in long.gaps()}


# -------------------------------------------------------------- trigger cadence

def test_a_meta_gem_does_not_change_the_socketed_spell_s_cadence(snapshots):
    """F-TRIG. The wrapped spell is scored exactly as if cast directly.

    PoB uses a declared trigger rate when the skill data carries one. No meta
    gem in the pinned catalog marked the socketed spell triggered, so the
    cadence of the trigger is absent from every output.
    """
    direct = snapshots["cast_direct"]
    wrapped = snapshots["cast_wrapped"]

    assert direct.loaded.main_skill == "Fireball"
    assert wrapped.loaded.main_skill == "Fireball"
    assert (declared(wrapped, "use_rate_per_second").value
            == pytest.approx(declared(direct, "use_rate_per_second").value))
    assert (declared(wrapped, "hit_damage_per_second").value
            == pytest.approx(declared(direct, "hit_damage_per_second").value))
    assert "trigger_rate_per_second" in {g.primitive_id for g in wrapped.gaps()}


@pytest.mark.parametrize("meta", META_GEMS)
def test_no_meta_gem_in_the_pinned_catalog_declares_a_trigger_rate(snapshots, meta):
    """F-TRIG, for every meta gem that can wrap a spell, not just one."""
    direct = snapshots["cast_direct"]
    wrapped = snapshots[wrapped_name(meta)]

    assert wrapped.loaded.main_skill == direct.loaded.main_skill
    assert (declared(wrapped, "use_rate_per_second").value
            == pytest.approx(declared(direct, "use_rate_per_second").value))
    assert (declared(wrapped, "hit_damage_per_second").value
            == pytest.approx(declared(direct, "hit_damage_per_second").value))


# -------------------------------------------------------------------- cooldown

def test_a_cooldown_becomes_the_use_rate(snapshots):
    """F-CD. For a cooldown skill the rate is one use per cooldown."""
    snap = snapshots["cooldown"]
    cooldown = declared(snap, "cooldown_s")
    rate = declared(snap, "use_rate_per_second")
    use_time = declared(snap, "use_time_s")

    assert cooldown.unit == "seconds"
    assert rate.value == pytest.approx(1.0 / cooldown.value, rel=1e-9)
    assert use_time.value == pytest.approx(cooldown.value, rel=1e-9)


def test_a_skill_without_a_cooldown_reports_a_gap_not_a_zero(snapshots):
    """A zero cooldown would mean an unbounded use rate."""
    snap = snapshots["baseline"]

    assert snap.primitive("cooldown_s") is None
    gap = next(g for g in snap.gaps() if g.primitive_id == "cooldown_s")
    assert gap.kind == "missing_input"
    assert gap.native_key == "Cooldown"


# ---------------------------------------------------------- the ambiguous unit

def test_combined_dps_changes_unit_with_the_skill(snapshots):
    """F-UNIT. ``CombinedDPS`` is damage per use for a showAverage skill.

    Incinerate reports ``CombinedDPS`` equal to ``AverageDamage`` while
    ``TotalDPS`` is that number times the use rate. Reading the field as a DPS
    is wrong by a factor of the use rate, so the unit is resolved from the
    engine's own flag or the primitive is not supplied at all.
    """
    per_second = snapshots["baseline"]
    per_use = snapshots["show_average"]

    assert per_second.loaded.main_skill_show_average is False
    assert declared(per_second, "combined_damage").unit == "damage per second"

    assert per_use.loaded.main_skill_show_average is True
    combined = declared(per_use, "combined_damage")
    assert combined.unit == "damage per use"
    assert combined.value == pytest.approx(
        declared(per_use, "damage_per_use").value)
    assert declared(per_use, "hit_damage_per_second").value == pytest.approx(
        combined.value * declared(per_use, "use_rate_per_second").value)


def test_full_dps_aggregates_groups_and_includes_damage_over_time(snapshots):
    """F-FULL."""
    snap = snapshots["show_average"]
    total = declared(snap, "aggregate_damage_per_second")

    assert total.unit == "damage per second"
    assert total.value == pytest.approx(
        declared(snap, "hit_damage_per_second").value
        + declared(snap, "dot_damage_per_second").value, rel=1e-9)


# ------------------------------------------------------------ cost and radius

def test_the_cost_per_second_is_the_cost_per_use_times_the_rate(snapshots):
    """F-COST. Two costs with two units, both named."""
    snap = snapshots["baseline"]
    per_use = declared(snap, "mana_cost_per_use")
    per_second = declared(snap, "mana_cost_per_second")

    assert per_use.unit == "mana per use"
    assert per_second.unit == "mana per second"
    assert per_second.value == pytest.approx(
        per_use.value * declared(snap, "use_rate_per_second").value, rel=1e-9)


def test_the_radius_carries_pobs_own_metre_conversion(snapshots):
    """F-AREA. contracts.md forbids assuming the raw radius is metres."""
    snap = snapshots["baseline"]
    raw = declared(snap, "area_of_effect_radius_pob")
    metres = declared(snap, "area_of_effect_radius_m")

    assert "10 units per metre" in raw.unit
    assert metres.unit == "metres"
    assert metres.value == pytest.approx(raw.value / 10.0)


# ---------------------------------------------------------------- the contract

def test_every_declared_primitive_has_one_owner_and_one_unit(snapshots):
    for name, snap in snapshots.items():
        assert snap.semantics_status == "declared", name
        for primitive_id, value in snap.declared().items():
            assert value.unit, (name, primitive_id)
            assert value.definition.owner == "pob", (name, primitive_id)
        for gap in snap.gaps():
            assert gap.explanation and gap.needed_evidence, (name, gap)


def test_what_pob_does_not_supply_is_always_a_gap(snapshots):
    """The encounter-level primitives P07 owns are never filled in here."""
    for name, snap in snapshots.items():
        gaps = {g.primitive_id for g in snap.gaps()}
        for primitive_id in ("targets_hit_per_use", "trigger_rate_per_second",
                             "projectile_overlap_multiplier",
                             "sustained_damage_per_second", "setup_time_s"):
            assert primitive_id in gaps, (name, primitive_id)
            assert snap.primitive(primitive_id) is None, (name, primitive_id)
