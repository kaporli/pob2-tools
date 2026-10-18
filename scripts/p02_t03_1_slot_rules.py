"""Regenerate the P02-T03.1 evidence: engine slot rules and a real item pool.

Writes under `docs/evidence/P02-T03.1/`:

* `slot-acceptance.json` - the engine's slot acceptance probe as returned in
  `rule_sources.slotAcceptance`, with the checkout it was read from. The
  offline tests derive the slot rules from this capture.
* `slot-rules.json` - the slot rules, off-hand rules and P02-T03.1 gaps the
  exporter built from it.
* `real-pool.json` - a pool built from real item text: the owner's seed
  character (owned, in its source slots) and the poe.ninja reference build
  25c49 (an imported guide, not owned, availability unknown).

Everything is PoB-derived. Nothing here is a gameplay measurement, and an
item being placeable in a slot says nothing about its value.

Usage:
    POB2_ROOT=<clean checkout of the pin> python scripts/p02_t03_1_slot_rules.py

Refuses a dirty or missing checkout.
"""

from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _pkg in ("pob2-optimizer", "pob2-mcp"):
    sys.path.insert(0, str(REPO_ROOT / _pkg))

OUT = REPO_ROOT / "docs" / "evidence" / "P02-T03.1"
P02 = REPO_ROOT / "docs" / "evidence" / "P02"
SEED = REPO_ROOT / "docs" / "evidence" / "P09-T01.1" / "seed" / "items-raw.json"
NINJA = (REPO_ROOT / "docs" / "evidence" / "P09-T01.1" / "reference-ninja-25c49"
         / "decoded.xml")
NOT_A_CLAIM = (
    "Read out of the pinned Path of Building checkout. Which slot accepts "
    "which base is the engine's ItemsTab:IsItemValidForSlot, not a statement "
    "about the live game. Nothing here is a gameplay measurement.")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(name: str, payload) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=1, sort_keys=True,
                                       ensure_ascii=False) + "\n",
                            encoding="utf-8")


def real_item_texts() -> list[tuple[str, str, str]]:
    """(source, slot, item text) for every real item this evidence uses."""
    out = []
    for slot, text in sorted(json.loads(SEED.read_text(encoding="utf-8")).items()):
        out.append(("seed", slot, text))
    root = ET.parse(NINJA).getroot()
    items = {item.get("id"): "\n".join(line.strip() for line in
                                       (item.text or "").strip().splitlines())
             for item in root.findall(".//Items/Item")}
    placed = set()
    for item_set in root.findall(".//Items/ItemSet")[:1]:
        for slot in item_set.findall("Slot"):
            item_id = slot.get("itemId")
            if item_id and item_id != "0" and item_id in items:
                out.append(("ninja-25c49", slot.get("name"), items[item_id]))
                placed.add(item_id)
    for socket in root.findall(".//Tree/Spec/Sockets/Socket"):
        item_id = socket.get("itemId")
        if item_id and item_id != "0" and item_id in items:
            out.append(("ninja-25c49", "Jewel %s" % socket.get("nodeId"),
                        items[item_id]))
            placed.add(item_id)
    for item_id, text in sorted(items.items()):
        if item_id not in placed:
            out.append(("ninja-25c49", None, text))
    return out


def main() -> int:
    pob_root = os.environ.get("POB2_ROOT")
    if not pob_root or not Path(pob_root).is_dir():
        print("POB2_ROOT must name a clean PoB checkout", file=sys.stderr)
        return 2

    from pob2opt.catalog import (EngineCatalogReader, ExportRequest,
                                 PobCatalogProvider, load_release_capture)
    from pob2opt.catalog.slotrules import accepts, base_category
    from pob2opt.catalog.sources import read_citations
    from pob2opt.domain.absent import Absent
    from pob2opt.evaluation import (BuildDocument, EngineAdapter, EngineState,
                                    pob_worker_spec, resolve_checkout)
    from pob2opt.market.importer import import_market
    from collections import Counter

    from pob2opt.market.pools import (OwnedItem, build_pool, pool_report,
                                      stat_known)
    from pob2opt.parsers.pob import ParseContext

    checkout = resolve_checkout(pob_root)
    if checkout.dirty_hash is not None:
        print("checkout %s is dirty; refusing" % pob_root, file=sys.stderr)
        return 2
    request = ExportRequest.from_file(P02 / "catalog-profile-request.json")
    captures = [load_release_capture(path)
                for path in sorted((P02 / "release").glob("*.json"))]
    citations = read_citations(pob_root)
    before = os.getcwd()
    adapter = EngineAdapter(pob_worker_spec(pob_root), checkout=checkout,
                            start_timeout_s=600.0, screen_timeout_s=300.0,
                            detailed_timeout_s=300.0)
    try:
        reader = EngineCatalogReader(adapter, timeout_s=600.0)

        def behaviour(fixture):
            document = BuildDocument(
                build_hash="compat/%s" % fixture["fixture_id"],
                xml=fixture["document"])
            state = EngineState(
                stat_keys=tuple(sorted(fixture.get("expected") or {})))
            return adapter.probe(document, state, timeout_s=300.0)

        provider = PobCatalogProvider(
            reader, citations=citations, release_captures=captures,
            pob_commit=checkout.commit, pob_dirty_hash=checkout.dirty_hash,
            behaviour=behaviour)
        export = provider.export(request)
        probe = reader.rule_sources().get("slotAcceptance")
    finally:
        adapter.close()
        os.chdir(before)

    OUT.mkdir(parents=True, exist_ok=True)
    recorded = {"pob_commit": checkout.commit,
                "pob_dirty_hash": checkout.dirty_hash,
                "written_at": _now(), "kind": "PoB-derived",
                "not_a_claim": NOT_A_CLAIM}
    _write("slot-acceptance.json", {**recorded, "slotAcceptance": probe})

    profile, catalog = export.profile, export.catalog
    rules = profile.character_rules
    off_hand = rules.weapon_sets.off_hand_rules
    t031 = [gap for gap in export.gaps if gap.gap_id.startswith("gap/p02-t03.1/")]
    _write("slot-rules.json", {
        **recorded,
        "catalog_hash": catalog.catalog_hash,
        "patch_profile_id": profile.record_id,
        "slots": {rule.slot_id: rule.accepted_base_categories
                  for rule in rules.slots},
        "undecided": {rule.slot_id: {
            "categories": rule.undecided_categories,
            "rarities": rule.undecided_rarities,
            "bases": rule.undecided_bases}
            for rule in rules.slots
            if not isinstance(rule.undecided_categories, Absent)
            and (rule.undecided_categories or rule.undecided_rarities
                 or rule.undecided_bases)},
        "refused_rarities": {rule.slot_id: rule.refused_rarities
                             for rule in rules.slots
                             if not isinstance(rule.refused_rarities, Absent)
                             and rule.refused_rarities},
        "off_hand_rules": ([] if isinstance(off_hand, Absent) else [
            {"off_hand_slot_id": r.off_hand_slot_id,
             "main_hand_slot_id": r.main_hand_slot_id,
             "main_hand_category": r.main_hand_category,
             "required_flag": r.required_flag,
             "accepted_base_categories": r.accepted_base_categories,
             "refused_rarities": r.refused_rarities}
            for r in off_hand]),
        "gaps": [{"gap_id": g.gap_id, "kind": g.kind.value,
                  "severity": g.severity.value, "subject_ids": g.subject_ids,
                  "explanation": g.explanation} for g in t031],
        "open_rule_gap_ids": rules.missing_rule_gap_ids,
        "validation_errors": export.validation_errors,
    })

    # -- a pool from real item text ---------------------------------------
    from pob2opt.domain.enums import AccessMethod, Redistribution
    from pob2opt.domain.records import SCHEMA_VERSION, SourceDocument
    import hashlib

    created = _now()
    context = ParseContext(catalog_hash=catalog.catalog_hash, created_at=created,
                           entities=catalog.entities)
    raws = {e.entity_id: e.raw_reference
            for e in catalog.entities.get("item_bases", ())}
    items, owned_slots, rows = {}, {}, []
    for index, (source, slot, text) in enumerate(real_item_texts()):
        payload = text.encode("utf-8")
        document = SourceDocument(
            schema_version=SCHEMA_VERSION,
            record_id="src/p02-t03.1/%s/%02d" % (source, index),
            created_at=created, provenance_ids=[], provider="local",
            source_url=None, external_id=None, acquired_at=created,
            published_at=None, updated_at=None,
            access_method=AccessMethod.LOCAL_FILE, media_type="text/plain",
            blob_hash=hashlib.sha256(payload).hexdigest(),
            byte_count=len(payload), acquisition_version="p02-t03.1",
            source_manifest_id="local", declared_patch=None, author_id=None,
            locale=None, popularity=[], redistribution=Redistribution.RESTRICTED)
        result = import_market(document, payload, context)
        row = {"source": source, "source_slot": slot,
               "parse_status": result.result.status.value,
               "item_hash": None, "base_id": None, "category": None,
               # Why a record is partial: the importer's own issues.
               "issues": [{"code": i.code, "at": i.source_locator}
                          for i in result.result.issues]}
        for item in result.items:
            items[item.item_hash] = item
            row.update(item_hash=item.item_hash, base_id=item.base_id,
                       category=base_category(raws.get(item.base_id)),
                       item_parse_status=item.parse_status.value,
                       rarity=item.rarity,
                       line_statuses=dict(Counter(
                           m.parse_status.value for m in item.modifiers)),
                       unresolved_lines=[m.text for m in item.modifiers
                                         if m.parse_status.value
                                         == "unresolved"],
                       stat_known=stat_known(item),
                       fits=sorted(r.slot_id for r in rules.slots
                                   if accepts(r.accepted_base_categories,
                                              raws.get(item.base_id))))
            if source == "seed" and slot:
                owned_slots.setdefault(item.item_hash, []).append(slot)
        rows.append(row)

    # The seed is the owner's own character (account import), so its items
    # are owned. The reference build is a guide: nothing in it is owned.
    owned = [OwnedItem(item_hash=h, count=len(s), slot_ids=tuple(sorted(s)))
             for h, s in sorted(owned_slots.items())]
    pool = build_pool(catalog=catalog, profile=profile,
                      items=list(items.values()), owned=owned,
                      gaps=export.gaps, created_at=created,
                      provenance_ids=["p02-t03.1/evidence"])
    report = pool_report(pool)
    # Why each empty slot is empty: the real items whose category fits it,
    # and their parse status. A partial item is never placed.
    empty_reasons = {}
    for slot in pool.slots:
        if slot.status.value != "empty":
            continue
        fitting = [r for r in rows if slot.slot_id in (r.get("fits") or ())]
        empty_reasons[slot.slot_id] = (
            [{"source": r["source"], "source_slot": r["source_slot"],
              "item_parse_status": r.get("item_parse_status")}
             for r in fitting]
            or "no real input item has an accepted category")
    slots_out = {}
    for slot in pool.slots:
        if slot.candidates:
            slots_out[slot.slot_id] = {
                "status": slot.status.value,
                "candidates": [{"item_hash": c.item_hash,
                                "availability": c.availability.value,
                                "base_id": items[c.item_hash].base_id,
                                "retained_for": c.retained_for}
                               for c in slot.candidates]}
    _write("real-pool.json", {
        **recorded,
        "catalog_hash": catalog.catalog_hash,
        "inputs": rows,
        "owned_policy": "seed items owned in their source slots (account "
                        "import of the owner's character); reference-build "
                        "items not owned, availability unknown",
        "pool_id": pool.pool_id,
        "report": report,
        "slots_with_candidates": slots_out,
        "empty_slot_reasons": empty_reasons,
    })
    print("wrote %s" % OUT, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
