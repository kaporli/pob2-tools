"""Turning the P02-T03 fixture files into records (shared by both lanes).

The invented world in `tests/fixtures/legality/p02_t03_world.json` is handed
to the **real P02-T02 exporter**, so the `CharacterRules` the validator reads
are produced by the catalog code and not written here. The citations are the
real ones captured from the pinned checkout, so the level cap, the point
maximums and the support limit are the engine's numbers.

Nothing in this module decides a verdict or consults the validator. It builds
records from JSON; the expectations live in the fixture file next to the case
they belong to.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from pob2opt.catalog import ExportRequest, MappingCatalogReader, PobCatalogProvider
from pob2opt.catalog.sources import citations_from_payload
from pob2opt.domain.enums import ModifierCategory, ModifierParseStatus, RecordParseStatus
from pob2opt.domain.records import (SCHEMA_VERSION, BuildSpec, EquipmentSlot,
                                    ItemInstance, ItemModifier, Passives,
                                    Progression, SkillEntry, SkillGroup, Socket,
                                    SocketedEntity, WeaponSet)
from pob2opt.evaluation.legality import ImportedState, MeasuredState, PoolState

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "legality"
WORLD = FIXTURES / "p02_t03_world.json"
CASES = FIXTURES / "p02_t03_cases.json"
#: Real citations from the pinned checkout, captured by P02-T02.
SLICE = REPO_ROOT / "docs" / "evidence" / "P02" / "catalog-rows-slice.json"

#: No compatibility fixture applies to an invented world. An empty set keeps
#: the export honest about that rather than reporting absences as regressions.
NO_FIXTURES = {"fixture_set_version": 0, "recorded_from": {}, "fixtures": []}


def load_world() -> Any:
    """Export the invented world through the real P02-T02 exporter."""
    world = json.loads(WORLD.read_text(encoding="utf-8"))
    citations = citations_from_payload(
        json.loads(SLICE.read_text(encoding="utf-8"))["citations"])
    provider = PobCatalogProvider(
        MappingCatalogReader(world["tables"], world["rule_sources"],
                             source=str(WORLD)),
        citations=citations,
        pob_commit="0000000000000000000000000000000000000000",
        pob_dirty_hash=None,
        fixtures=NO_FIXTURES,
        clock=lambda: "2026-10-06T00:00:00Z")
    return provider.export(ExportRequest(game="poe2", realm="poe2",
                                         league_id="Invented"))


def load_cases() -> dict:
    return json.loads(CASES.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ records ---

def node_ids(spec: Mapping[str, Any], key: str) -> list[str]:
    out = [str(value) for value in spec.get(key) or ()]
    span = spec.get("%s_range" % key)
    if span:
        out.extend(str(value) for value in range(int(span[0]), int(span[1])))
    return out


def make_item(item_hash: str, spec: Mapping[str, Any]) -> ItemInstance:
    modifiers = []
    for position, raw in enumerate(spec.get("modifiers") or ()):
        modifiers.append(ItemModifier(
            category=ModifierCategory(raw.get("category", "explicit")),
            source_position=position,
            text=raw.get("text", "invented modifier"),
            native_id=raw.get("native_id"),
            resolved_effect_ids=list(raw.get("resolved_effect_ids") or ()),
            values=[],
            flags={},
            parse_status=ModifierParseStatus(raw.get("parse_status", "resolved"))))
    sockets = [Socket(socket_id="%s/%d" % (item_hash, index), group=0,
                      colour=None, contents_id=None)
               for index in range(int(spec.get("sockets", 0)))]
    return ItemInstance(
        schema_version=SCHEMA_VERSION,
        record_id="item/%s" % item_hash,
        created_at="2026-10-06T00:00:00Z",
        provenance_ids=[],
        item_hash=item_hash,
        catalog_hash=spec["catalog_hash"],
        base_id=spec.get("base_id"),
        display_name=spec.get("display_name", item_hash),
        rarity=spec.get("rarity", "rare"),
        item_level=spec.get("item_level"),
        requirements={k: int(v) for k, v in (spec.get("requirements") or {}).items()},
        properties={},
        modifiers=modifiers,
        sockets=sockets,
        flags={},
        raw_text=spec.get("raw_text"),
        source_document_id=spec.get("source_document_id"),
        parse_status=RecordParseStatus(spec.get("parse_status", "complete")))


def make_items(cases: Mapping[str, Any], catalog_hash: str) -> dict[str, ItemInstance]:
    return {item_hash: make_item(item_hash, {**spec, "catalog_hash": catalog_hash})
            for item_hash, spec in (cases.get("items") or {}).items()}


def _skill(raw: Mapping[str, Any]) -> SkillEntry:
    return SkillEntry(
        skill_id=raw["skill_id"],
        gem_id=raw.get("gem_id"),
        level=int(raw.get("level", 1)),
        quality=int(raw.get("quality", 0)),
        enabled=bool(raw.get("enabled", True)),
        support_ids=list(raw.get("supports") or ()),
        triggered=[_skill(nested) for nested in raw.get("triggered") or ()])


def make_build(spec: Mapping[str, Any], *, catalog_hash: str,
               build_hash: str = "build/p02-t03") -> BuildSpec:
    progression = spec.get("progression") or {}
    equipment: dict[str, EquipmentSlot | None] = {}
    for slot, entry in (spec.get("equipment") or {}).items():
        if entry is None:
            equipment[slot] = None
        else:
            equipment[slot] = EquipmentSlot(item_hash=entry["item"],
                                            listing_id=entry.get("listing"))
    weapon_sets = [
        WeaponSet(set_id=raw["set_id"],
                  hand_slots={hand: slot for hand, slot
                              in (raw.get("hands") or {}).items()},
                  passive_allocations=node_ids(raw, "passives"))
        for raw in spec.get("weapon_sets") or ()]
    groups = [
        SkillGroup(group_id=raw.get("group_id", "group-%d" % index),
                   enabled=bool(raw.get("enabled", True)),
                   slot_id=raw.get("slot"),
                   source_item_hash=raw.get("source_item"),
                   weapon_set_id=raw.get("weapon_set"),
                   main_skill_index=raw.get("main_skill_index"),
                   skills=[_skill(skill) for skill in raw.get("skills") or ()])
        for index, raw in enumerate(spec.get("skill_groups") or ())]
    return BuildSpec(
        schema_version=SCHEMA_VERSION,
        record_id=build_hash,
        created_at="2026-10-06T00:00:00Z",
        provenance_ids=[],
        build_hash=build_hash,
        catalog_hash=catalog_hash,
        declared_patch=None,
        name=spec.get("name", "fixture build"),
        class_id=spec["class_id"],
        ascendancy_id=spec.get("ascendancy_id"),
        level=int(spec["level"]),
        progression=Progression(
            quest_flags={}, reward_flags={},
            normal_point_budget=progression.get("normal"),
            ascendancy_point_budget=progression.get("ascendancy"),
            evidence_ids=list(progression.get("evidence_ids") or ())),
        equipment=equipment,
        weapon_sets=weapon_sets,
        passives=Passives(
            allocated=node_ids(spec, "allocated"),
            ascendancy_allocated=node_ids(spec, "ascendancy_allocated"),
            choices={str(k): str(v) for k, v in (spec.get("choices") or {}).items()},
            socketed=[SocketedEntity(node_id=str(raw["node_id"]),
                                     entity_id=raw["entity_id"])
                      for raw in spec.get("socketed") or ()]),
        skill_groups=groups,
        config={},
        rotation_ids=[],
        source_document_ids=[],
        variant_id=None,
        family_id=None,
        raw_blob_hashes=[],
        parse_status=RecordParseStatus(spec.get("parse_status", "complete")),
        unresolved_refs=[])


def make_measured(spec: Mapping[str, Any] | None) -> MeasuredState | None:
    if spec is None:
        return None
    pools = {name: PoolState(pool=name, total=raw.get("total"),
                             reserved=raw.get("reserved"),
                             unreserved=raw.get("unreserved"))
             for name, raw in (spec.get("pools") or {}).items()}
    return MeasuredState(
        source=spec.get("source", "fixture"),
        attributes={name: spec.get(name) for name
                    in ("strength", "dexterity", "intelligence")
                    if spec.get(name) is not None},
        pools=pools)


def make_imported(spec: Mapping[str, Any] | None, *,
                  build_hash: str) -> ImportedState | None:
    """Build an ImportedState through the production wire parser.

    The payload below is shaped exactly as the `legality_state` handler
    answers, so the offline lane exercises the same parsing the engine lane
    does.
    """
    if spec is None:
        return None
    payload = {
        "class": spec.get("class_name"),
        "classId": spec.get("class_id"),
        "ascendancy": spec.get("ascendancy_name"),
        "ascendClassId": spec.get("ascendancy_id"),
        "level": spec.get("level"),
        "allocatedNodes": list(spec.get("allocated") or ()),
        "ascendancyNodes": list(spec.get("ascendancy_allocated") or ()),
        "unreadableNodeKeys": list(spec.get("unreadable") or ()),
        "classStartNode": spec.get("class_start_node"),
        "pointsUsed": spec.get("points_used"),
        "ascendancyPointsUsed": spec.get("ascendancy_points_used"),
        "weaponSet1PointsUsed": spec.get("weapon_set_1_points"),
        "weaponSet2PointsUsed": spec.get("weapon_set_2_points"),
        "items": {slot: dict(raw) for slot, raw
                  in (spec.get("items") or {}).items()},
        "socketGroups": list(spec.get("socket_groups") or ()),
        "pools": [{"pool": name.capitalize(), **raw} for name, raw
                  in (spec.get("pools") or {}).items()],
        "attributes": [{"attribute": key, "value": spec.get(name)}
                       for key, name in (("Str", "strength"),
                                         ("Dex", "dexterity"),
                                         ("Int", "intelligence"))],
        "calculated": bool(spec.get("calculated", True)),
    }
    return ImportedState.from_wire(
        payload, document_hash=spec.get("document_hash", "0" * 64),
        build_hash=build_hash)
