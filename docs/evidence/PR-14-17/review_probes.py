"""Independent offline probes of PRs 14-17; no game or market observations.

Usage: python review_probes.py PR_NUMBER CHECKOUT
JSON reports observed behavior, including defects; exit zero means it ran.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from dataclasses import replace

pr = int(sys.argv[1])
repo = Path(sys.argv[2]).resolve()
sys.path[:0] = [str(repo / "pob2-optimizer"), str(repo / "pob2-mcp"),
                str(repo / "tests"), str(repo / "scripts")]


def probe15():
    import p05_fixtures as fx
    from pob2opt.market.importer import import_market
    from pob2opt.parsers.dispatch import read_item_text
    from pob2opt.evaluation import export_item
    from pob2opt.parsers.resolve import naming_from_catalog
    from pob2opt.domain.validation import validate_record

    out = {}
    for stamp in ["2026-02-30T18:00:00Z", "2026-13-16T25:00:00Z"]:
        data = fx.capture_data()
        data["observed_at"] = stamp
        for entry in data["entries"]:
            if entry.get("listing"):
                entry["listing"].pop("observed_at", None)
        payload = fx.capture_bytes(data)
        result = import_market(fx.document(payload), payload, fx.context())
        out[stamp] = {"status": result.result.status.value,
                      "observed_at": [l.observed_at for l in result.listings],
                      "validation": [validate_record(l).ok for l in result.listings]}

    raw = fx.game_items()["ring_shared_name_a"]
    for name, changed in {
        "unterminated_reminder": raw.replace("+21 to Dexterity", "(unterminated reminder\n+21 to Dexterity"),
        "unidentified": raw.replace("Adds 9 to 15 Cold damage to Attacks\n+21 to Dexterity", "Unidentified"),
    }.items():
        read = read_item_text(changed, fx.document(changed.encode()), fx.context(), record_id="probe")
        text, losses = export_item(read.item, naming_from_catalog(fx.context().entities).naming)
        out[name] = {"status": read.status.value, "item_status": read.item.parse_status.value,
                     "modifiers": [m.text for m in read.item.modifiers],
                     "issues": [i.code for i in read.issues],
                     "export_completeness": losses.report().completeness}
    return out


def probe16():
    import legality_fixtures as lf
    from pob2opt.domain.enums import RecordParseStatus, Availability
    from pob2opt.domain.records import EquipmentSlot, Listing
    from pob2opt.domain.identity import item_hash
    from pob2opt.market.pools import build_pool, owned_from_build, equipment_conflicts

    world = lf.load_world()
    profile = replace(world.profile, character_rules=replace(
        world.profile.character_rules, slots=[replace(r, accepted_base_categories=["Ring"])
          if r.slot_id in ("poe2/slots/Ring 1", "poe2/slots/Ring 2") else r
          for r in world.profile.character_rules.slots]))
    base = lf.make_item("a" * 64, {"catalog_hash": world.catalog.catalog_hash,
                        "base_id": "poe2/item_bases/Iron Ring", "requirements": {"level": 1}})
    current = replace(base, item_hash=item_hash(base), parse_status=RecordParseStatus.COMPLETE)
    stale = replace(current, catalog_hash="f" * 64)
    partial = replace(current, parse_status=RecordParseStatus.PARTIAL)

    def pool(items, owned=()):
        return build_pool(catalog=world.catalog, profile=profile, items=items,
                          owned=owned, created_at="2026-10-18T00:00:00Z")

    def candidates(p):
        return [(s.slot_id, [c.item_hash for c in s.candidates]) for s in p.slots if s.candidates]

    out = {"pool_catalog": world.catalog.catalog_hash, "stale_item_catalog": stale.catalog_hash,
           "stale_candidates": candidates(pool([stale])),
           "partial_then_complete": candidates(pool([partial, current])),
           "complete_then_partial": candidates(pool([current, partial]))}
    foreign_listing = Listing(
        schema_version=1, record_id="listing/foreign", created_at="2026-10-18T00:00:00Z",
        provenance_ids=[], listing_id="listing/foreign", provider="synthetic",
        realm="not-" + profile.realm, league_id="not-" + str(profile.league_id),
        item_hash=current.item_hash, price_amount="1", price_currency="divine",
        listed_at=None, observed_at="2026-10-18T00:00:00Z",
        last_checked_at="2026-10-18T00:00:00Z", availability=Availability.OBSERVED,
        listing_url=None, source_document_id="synthetic/source", quantity=1)
    foreign_pool = build_pool(catalog=world.catalog, profile=profile, items=[current],
                             listings=[foreign_listing], created_at="2026-10-18T00:00:00Z")
    out["profile_market_scope"] = [profile.realm, profile.league_id]
    out["listing_market_scope"] = [foreign_listing.realm, foreign_listing.league_id]
    out["foreign_listing_candidates"] = [(s.slot_id, c.listing_id) for s in foreign_pool.slots
                                          for c in s.candidates if c.listing_id]
    build = lf.make_build({"class_id": "poe2/classes/1", "level": 10}, catalog_hash=world.catalog.catalog_hash)
    unlisted_build = replace(build, equipment={"Ring 1": EquipmentSlot(current.item_hash, None),
                                               "Ring 2": EquipmentSlot(current.item_hash, None)})
    inferred_owned = owned_from_build(unlisted_build)
    out["unlisted_duplicate_inferred_owned"] = [{"count": i.count, "hash": i.item_hash} for i in inferred_owned]
    out["duplicate_conflicts_without_ownership"] = [c.code for c in equipment_conflicts(unlisted_build)]
    out["duplicate_conflicts_with_inferred_ownership"] = [c.code for c in equipment_conflicts(unlisted_build, owned=inferred_owned)]
    return out


def probe14():
    from pob2opt.catalog.release import load_release_capture, ReleaseCaptureError
    from pob2opt.catalog.supports import flicker_coverage
    capture = repo / "docs/evidence/P02/release/poe2-0.5.5e-verbatim.json"
    original = json.loads(capture.read_text())
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)
        data = copy.deepcopy(original)
        data["raw_file"] = "page.html"
        (path / "page.html").write_bytes((capture.parent / original["raw_file"]).read_bytes() + b"tampered")
        (path / "capture.json").write_text(json.dumps(data))
        try:
            load_release_capture(path / "capture.json")
            refusal = None
        except ReleaseCaptureError as error:
            refusal = str(error)
    rows = json.loads((repo / "docs/evidence/P02/catalog-rows-slice.json").read_text())["tables"]
    good = flicker_coverage(rows["gems"], rows["granted_skills"])
    bad = copy.deepcopy(rows["granted_skills"])
    for row in bad:
        if row["id"] == "FlickerStrikePlayer":
            row.pop("supportedBy", None)
    return {"tampered_capture_refused": refusal, "original_coverage_issues": good["issues"],
            "missing_supports_issues": flicker_coverage(rows["gems"], bad)["issues"]}


def probe17():
    import p09_t01_1_flicker_suite as gen
    from pob2opt.domain.identity import content_hash
    suite = json.loads((repo / "benchmarks/p09-flicker-v1/suite.json").read_text())
    bundle = json.loads((repo / "benchmarks/p09-flicker-v1/scenarios.json").read_text())
    refs = json.loads((repo / "benchmarks/p09-flicker-v1/references.json").read_text())
    bad_hashes = [name for name, ref in suite["sources"].items()
                  if hashlib.sha256((repo / ref["path"]).read_bytes()).hexdigest() != ref["sha256"]]
    mutated = copy.deepcopy(bundle["scenarios"])
    dps = next(s for s in mutated if s["scenario_id"] == "flicker_sustained_v1")
    dps["fields"]["window_s"]["value"] = [0, 60]
    gaps = {g["gap_id"]: g for g in bundle["data_gaps"]}
    condition = gaps["gap-p09-t011-hit-and-run-movement"]
    method = gen.pob_cycle_method()
    return {"bad_source_hashes": bad_hashes,
            "changed_window_changes_suite_hash": content_hash(gen.suite_identity(mutated, refs)) != suite["suite_hash"],
            "activation_gap": condition,
            "activation_gap_listed_as_method_blocker": "gap-p09-t011-hit-and-run-movement" in method["status"],
            "speed_input": next(i for i in method["inputs"] if i["name"] == "S_F(c)")}


if __name__ == "__main__":
    print(json.dumps({"pr": pr, "observations": globals()["probe%d" % pr]()}, indent=2))
