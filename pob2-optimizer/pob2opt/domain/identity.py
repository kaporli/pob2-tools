"""Canonical serialization and content identity (P01-T02).

Identity is a projection, then a hash. For each record this module builds an
explicit *identity projection* - a plain dict holding only the fields that
define that thing - and hashes its canonical JSON. Anything not listed in the
projection cannot change the hash, which is the whole point: a display name,
a price or an acquisition timestamp must not fork a combat result, and a
support gem or an item roll must.

Canonical form: UTF-8 JSON, object keys sorted, compact separators, no NaN or
Infinity. ``ensure_ascii`` is off, so the bytes are the text.

Ordering rules, from contracts.md:

* Passive allocations are unordered. They are validated for duplicates first
  (``validation.py``) and then **sorted** here, so import order cannot fork
  identity.
* Skill groups, the skills inside them, their support lists and rotation rules
  are **ordered**. Their order is semantic and is preserved.

Included and excluded fields
----------------------------

``document_hash(payload)`` hashes the **raw bytes**, not canonical JSON. Two
payloads differing only in line endings are two different documents, because
a source byte difference is evidence.

``item_identity`` includes: base_id, rarity, item_level, requirements,
properties, every modifier (category, source position, text, native id,
resolved effect ids, value ranges, flags, parse status), sockets and item
flags. It excludes: display_name, raw_text, parse_status (derived from the
modifiers), source_document_id, catalog_hash and the base record fields.

Why ``catalog_hash`` is excluded: the item is identified by its resolved
content, and ``resolved_effect_ids`` already carries whatever the catalog
resolved. Catalog identity enters an evaluation through the cache key
(``cache.py``), where a catalog change must invalidate results, rather than
through the item hash, where it would fork every item on every patch bump.

``build_identity`` includes: class_id, ascendancy_id, level, progression
(quest and reward flags and both point budgets), equipment as slot to
item_hash, weapon sets with their hand slots and per-set allocations, passive
allocations and choices and socketed entities, every skill group with its
enabled flag, slot, source item, set binding, main-skill index and ordered
skills with their ordered supports and trigger nesting, and the gameplay
values of config. It excludes: name, variant_id, family_id, declared_patch,
catalog_hash, rotation_ids, source_document_ids, raw_blob_hashes,
parse_status, unresolved_refs, the base record fields, and - deliberately -
every ``listing_id``, so an equal-stat item bought at a different price has
the same combat identity.

BuildSpec schema version 2 versions the build identity. A version 2
projection adds ``identity_version: 2``, ``main_skill_group`` (which group
PoB evaluates) and, per skill, ``supports``: each support's id, gem id,
level, quality and enabled flag, in order. A version 1
projection is unchanged, so every stored version 1 hash still verifies. The
two can never collide: only version 2 carries the ``identity_version`` key.

``skill_group_id`` is excluded too: it is a structural label from the source
file, and two gameplay-identical builds that numbered their groups
differently are the same build.

``rotation_identity`` includes the category and the ordered rules (action,
action id, skill, target selector, weapon set, predicate). It excludes
rotation_id, name and version, which are labels.

``scenario_identity`` includes everything that changes what is simulated:
scenario_id, version, category, kind, targets, initial state, event schedule,
spatial and movement models, duration limit, completion condition, incoming
damage model, allowed preparation, rng seeds, the capability floor and the
survival and resource gates. It excludes evidence_ids, validation_status and
the reference build and result: a new reference changes aggregate scores, not
what a candidate's own evaluation computed, so it belongs to the baseline
suite hash instead.

``objective_identity`` (D07) includes the registered definition's fixed rules
(windows, metric names, score metric, tie-break rules), the target skill ids
sorted as a set, and the resolved benchmark scenario and attribution rule set
hashes. It excludes the two locator strings, which name where the content was
read from, and the class scope: classes are compared under one objective, so
the scope belongs to the request and the manifest, not the objective hash.

``pool_identity`` (P05-T03) is every field of an equipment pool except the
base record fields and ``pool_id``, which is derived from it.

``listing_snapshot_hash`` is the opposite projection: price, currency,
availability and the observation timestamps, which are exactly the fields the
combat hashes ignore.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .absent import ABSENT
from .codec import to_jsonable

#: Hex digest of the empty byte string, handy in fixtures and tests.
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def canonical_json(value: Any) -> bytes:
    """Canonical UTF-8 JSON bytes: sorted keys, compact, no NaN."""
    return canonical_text(value).encode("utf-8")


def canonical_text(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def content_hash(value: Any) -> str:
    """SHA-256 over canonical JSON of an already-projected plain value."""
    return hashlib.sha256(canonical_json(value)).hexdigest()


def document_hash(payload: bytes) -> str:
    """SHA-256 over raw bytes. Never normalizes line endings."""
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("document_hash takes raw bytes, not %s"
                        % type(payload).__name__)
    return hashlib.sha256(bytes(payload)).hexdigest()


def _json(value: Any) -> Any:
    return to_jsonable(value)


# --------------------------------------------------------------- items ===

def item_identity(item: Any) -> dict[str, Any]:
    return {
        "base_id": item.base_id,
        "rarity": item.rarity,
        "item_level": item.item_level,
        "requirements": dict(item.requirements),
        "properties": _json(item.properties),
        "modifiers": [
            {
                "category": modifier.category.value,
                "source_position": modifier.source_position,
                "text": modifier.text,
                "native_id": modifier.native_id,
                "resolved_effect_ids": list(modifier.resolved_effect_ids),
                "values": [_json(v) for v in modifier.values],
                "flags": dict(modifier.flags),
                "parse_status": modifier.parse_status.value,
            }
            for modifier in item.modifiers
        ],
        "sockets": [_json(socket) for socket in item.sockets],
        "flags": dict(item.flags),
    }


def item_hash(item: Any) -> str:
    return content_hash(item_identity(item))


def listing_snapshot_identity(listing: Any) -> dict[str, Any]:
    return {
        "listing_id": listing.listing_id,
        "provider": listing.provider,
        "realm": listing.realm,
        "league_id": listing.league_id,
        "item_hash": listing.item_hash,
        "price_amount": listing.price_amount,
        "price_currency": listing.price_currency,
        "listed_at": listing.listed_at,
        "observed_at": listing.observed_at,
        "last_checked_at": listing.last_checked_at,
        "availability": listing.availability.value,
        "quantity": listing.quantity,
    }


def listing_snapshot_hash(listing: Any) -> str:
    return content_hash(listing_snapshot_identity(listing))


def pool_identity(pool: Any) -> dict[str, Any]:
    """Everything an equipment pool holds except the base record fields and
    its own ID. Slot and candidate order is the builder's deterministic
    order and is kept."""
    return {
        "catalog_hash": pool.catalog_hash,
        "patch_profile_id": pool.patch_profile_id,
        "sampling": _json(pool.sampling),
        "slots": [_json(slot) for slot in pool.slots],
        "enabling_queries": [_json(query) for query in pool.enabling_queries],
        "unplaced_item_hashes": list(pool.unplaced_item_hashes),
        "gap_ids": list(pool.gap_ids),
    }


def pool_hash(pool: Any) -> str:
    return content_hash(pool_identity(pool))


# --------------------------------------------------------------- builds ===

#: The BuildSpec schema version whose identity carries support settings.
SUPPORT_IDENTITY_VERSION = 2


def _skill_identity(skill: Any, version: int) -> dict[str, Any]:
    out = {
        "skill_id": skill.skill_id,
        "gem_id": skill.gem_id,
        "level": skill.level,
        "quality": skill.quality,
        "enabled": skill.enabled,
        # Order is semantic: support order can change behaviour.
        "support_ids": list(skill.support_ids),
        "triggered": [_skill_identity(child, version)
                      for child in skill.triggered],
    }
    if version >= SUPPORT_IDENTITY_VERSION:
        supports = [] if skill.supports is ABSENT else skill.supports
        out["supports"] = [
            {"support_id": s.support_id, "gem_id": s.gem_id,
             "level": s.level, "quality": s.quality, "enabled": s.enabled}
            for s in supports]
    return out


def build_identity(build: Any) -> dict[str, Any]:
    passives = build.passives
    version = build.schema_version
    projection = {
        "class_id": build.class_id,
        "ascendancy_id": build.ascendancy_id,
        "level": build.level,
        "progression": {
            "quest_flags": dict(build.progression.quest_flags),
            "reward_flags": dict(build.progression.reward_flags),
            "normal_point_budget": build.progression.normal_point_budget,
            "ascendancy_point_budget": build.progression.ascendancy_point_budget,
        },
        # The listing is deliberately dropped: the item's properties are the
        # gameplay fact, the listing is how it was acquired.
        "equipment": {
            slot: (None if content is None else content.item_hash)
            for slot, content in build.equipment.items()
        },
        "weapon_sets": [
            {
                "set_id": weapon_set.set_id,
                "hand_slots": dict(weapon_set.hand_slots),
                "passive_allocations": sorted(weapon_set.passive_allocations),
            }
            for weapon_set in build.weapon_sets
        ],
        "passives": {
            "allocated": sorted(passives.allocated),
            "ascendancy_allocated": sorted(passives.ascendancy_allocated),
            "choices": dict(passives.choices),
            "socketed": sorted(
                ({"node_id": s.node_id, "entity_id": s.entity_id}
                 for s in passives.socketed),
                key=lambda s: (s["node_id"], s["entity_id"]),
            ),
        },
        "skill_groups": [
            {
                "enabled": group.enabled,
                "slot_id": group.slot_id,
                "source_item_hash": group.source_item_hash,
                "weapon_set_id": group.weapon_set_id,
                "main_skill_index": group.main_skill_index,
                "skills": [_skill_identity(s, version) for s in group.skills],
            }
            for group in build.skill_groups
        ],
        # Only the gameplay value. Where it came from and whether it has been
        # verified are provenance, not configuration.
        "config": {key: _json(value.value)
                   for key, value in build.config.items()},
    }
    if version >= SUPPORT_IDENTITY_VERSION:
        projection["identity_version"] = version
        projection["main_skill_group"] = (
            None if build.main_skill_group is ABSENT
            else build.main_skill_group)
    return projection


def build_hash(build: Any) -> str:
    return content_hash(build_identity(build))


# ------------------------------------------------- rotations and scenarios ===

def _predicate_identity(predicate: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"operator": predicate.operator.value}
    if predicate.operands is not ABSENT:
        out["operands"] = [_predicate_identity(p) for p in predicate.operands]
    if predicate.path is not ABSENT:
        out["path"] = predicate.path
    if predicate.value is not ABSENT:
        out["value"] = _json(predicate.value)
    return out


def rotation_identity(rotation: Any) -> dict[str, Any]:
    return {
        "category": rotation.category.value,
        # Priority order is the policy; it is never sorted.
        "rules": [
            {
                "action_id": rule.action_id,
                "action": rule.action.value,
                "skill_id": rule.skill_id,
                "target_selector": rule.target_selector,
                "weapon_set_id": rule.weapon_set_id,
                "predicate": _predicate_identity(rule.predicate),
            }
            for rule in rotation.rules
        ],
    }


def rotation_hash(rotation: Any) -> str:
    return content_hash(rotation_identity(rotation))


def scenario_identity(scenario: Any) -> dict[str, Any]:
    return {
        "scenario_id": scenario.scenario_id,
        "version": scenario.version,
        "category": scenario.category.value,
        "kind": scenario.kind.value,
        "target_entities": [_json(t) for t in scenario.target_entities],
        "initial_state": _json(scenario.initial_state),
        "event_schedule": [_json(e) for e in scenario.event_schedule],
        "spatial_model_id": scenario.spatial_model_id,
        "movement_model_id": scenario.movement_model_id,
        "duration_limit_s": scenario.duration_limit_s,
        "completion_condition": _json(scenario.completion_condition),
        "incoming_damage_model_id": scenario.incoming_damage_model_id,
        "allowed_preparation": _json(scenario.allowed_preparation),
        "rng_seeds": list(scenario.rng_seeds),
        "capability_floor_ratio": scenario.capability_floor_ratio,
        "survival_gates": [_json(g) for g in scenario.survival_gates],
        "resource_gates": [_json(g) for g in scenario.resource_gates],
    }


def scenario_hash(scenario: Any) -> str:
    return content_hash(scenario_identity(scenario))


def baseline_suite_identity(scenarios: list[Any]) -> dict[str, Any]:
    """The references a campaign is scored against.

    Separate from ``scenario_hash`` on purpose: freezing a new reference must
    start a new leaderboard without invalidating candidate evaluations.
    """
    return {
        "scenarios": sorted(
            (
                {
                    "scenario_id": s.scenario_id,
                    "version": s.version,
                    "scenario_hash": scenario_hash(s),
                    "reference_build_id": s.reference_build_id,
                    "reference_result_id": s.reference_result_id,
                }
                for s in scenarios
            ),
            key=lambda s: (s["scenario_id"], s["version"]),
        )
    }


def baseline_suite_hash(scenarios: list[Any]) -> str:
    return content_hash(baseline_suite_identity(scenarios))


# ------------------------------------------------------------ objectives ===

class UnresolvedObjective(ValueError):
    """An objective selection whose required content hashes are still null."""


def objective_identity(selection: Any) -> dict[str, Any]:
    """The identity of a RunRequest version 2 ``ObjectiveSelection``.

    Raises ``UnknownObjective`` for an unregistered id/version and
    ``UnresolvedObjective`` when the objective needs a benchmark and its
    hashes are not resolved yet: a request file is not a frozen objective.
    """
    from .objectives import definition_identity, get_objective

    definition = get_objective(selection.objective_id,
                               selection.objective_version)
    if definition.requires_benchmark:
        missing = [name for name in ("benchmark_scenario_hash",
                                     "attribution_rules_hash")
                   if getattr(selection, name) is None]
        if missing:
            raise UnresolvedObjective(
                "objective %s v%d has no identity until %s %s resolved"
                % (definition.objective_id, definition.version,
                   " and ".join(missing),
                   "is" if len(missing) == 1 else "are"))
    return {
        "definition": definition_identity(definition),
        "target_skill_ids": sorted(selection.target_skill_ids),
        "benchmark_scenario_hash": selection.benchmark_scenario_hash,
        "attribution_rules_hash": selection.attribution_rules_hash,
    }


def objective_hash(selection: Any) -> str:
    return content_hash(objective_identity(selection))


# ------------------------------------------------------------- manifests ===

def manifest_hash(manifest: Any) -> str:
    """Hash of the whole manifest, including its creation metadata.

    A manifest is the frozen description of one run, so unlike a build it has
    no metadata to exclude: the checkpoint validates against exactly these
    bytes.
    """
    return content_hash(_json(manifest))
