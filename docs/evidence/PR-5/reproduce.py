"""Independent review probes for PR #5 at 3d7ba53; synthetic inputs only.

Run from the repository root: python docs/evidence/PR-5/reproduce.py
These assertions document observed defects, not desired acceptance behavior.
"""
import copy
import json
import sys
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "pob2-optimizer"), str(ROOT / "tests")]

import legality_fixtures as lf
from p02_t05_fixtures import SYNTHETIC_NAMING, supported_build
from pob2opt.evaluation import export_build, import_build, round_trip
from pob2opt.evaluation.legality import LegalityValidator
from pob2opt.catalog import ExportRequest, MappingCatalogReader, PobCatalogProvider
from pob2opt.catalog.release import load_release_capture, load_release_captures
from pob2opt.catalog.sources import citations_from_payload

build, items = supported_build()
xml = export_build(build, items, SYNTHETIC_NAMING).xml


def read(root):
    return import_build(ET.tostring(root, encoding="unicode"), SYNTHETIC_NAMING,
                        record_id="review", created_at=build.created_at,
                        catalog_hash=build.catalog_hash)


results = {}
# Add a known, distinct second variant, and explicitly select it in PoB XML.
root = ET.fromstring(xml)
skills = root.find("Skills")
second = copy.deepcopy(skills.find("SkillSet"))
second.set("id", "2")
second.find("Skill").set("label", "ACTIVE SECOND VARIANT")
skills.append(second)
skills.set("activeSkillSet", "2")
parsed = read(root)
results["active_variant"] = {
    "active_id": "2", "expected_label": "ACTIVE SECOND VARIANT",
    "actual_label": parsed.build.skill_groups[0].group_id,
    "parse_status": parsed.build.parse_status.value,
}
assert parsed.build.skill_groups[0].group_id != "ACTIVE SECOND VARIANT"

# Add unresolved gameplay content to otherwise supported input.
root = ET.fromstring(xml)
root.find("Tree/Spec").set("nodes", "101,102,103,104,201,99999999")
ET.SubElement(root.find("Skills/SkillSet/Skill"), "Gem", {
    "skillId": "UnknownReviewSkill", "level": "20", "quality": "20",
    "enabled": "true"})
parsed = read(root)
report = round_trip(parsed.build, parsed.items, SYNTHETIC_NAMING)
results["unknown_content"] = {
    "parse_status": parsed.build.parse_status.value,
    "unresolved_refs": parsed.build.unresolved_refs,
    "unknown_node_retained": any("99999999" in s for s in parsed.build.passives.allocated),
    "unknown_skill_retained": any(s.skill_id == "UnknownReviewSkill"
                                  for g in parsed.build.skill_groups for s in g.skills),
    "roundtrip_status": report.status,
    "recommended_deliverable": report.recommended_deliverable,
}
assert parsed.build.parse_status.value == "complete"
assert not parsed.build.unresolved_refs
assert report.recommended_deliverable

# A disabled support is re-enabled; quality and level are also discarded.
root = ET.fromstring(xml)
support = root.find("Skills/SkillSet/Skill/Gem[@skillId='FixtureSupportTempo']")
support.attrib.update(enabled="false", level="7", quality="19")
parsed = read(root)
report = round_trip(parsed.build, parsed.items, SYNTHETIC_NAMING)
after = ET.fromstring(report.document).find(
    "Skills/SkillSet/Skill/Gem[@skillId='FixtureSupportTempo']")
results["support_state"] = {
    "before": dict(support.attrib), "after": dict(after.attrib),
    "roundtrip_status": report.status,
    "recommended_deliverable": report.recommended_deliverable,
}
assert after.get("enabled") == "true"
assert report.recommended_deliverable

# Capture an older release after a newer release: capture time is not live order.
capture = load_release_capture(ROOT / "docs/evidence/P02/release/poe2-0.5.5e.json")
newer = replace(capture, path="newer.json", patch_id="0.5.5e",
                patch_published_at="2026-10-01T00:00:00Z", captured_at="2026-10-02T00:00:00Z")
older = replace(capture, path="older.json", patch_id="0.5.4",
                patch_published_at="2026-09-01T00:00:00Z", captured_at="2026-10-03T00:00:00Z")
with patch.object(Path, "is_dir", return_value=True), \
     patch.object(Path, "glob", return_value=[Path("newer.json"), Path("older.json")]), \
     patch("pob2opt.catalog.release.load_release_capture", side_effect=[newer, older]):
    ordered = load_release_captures("synthetic-review-input")
world = json.loads(lf.WORLD.read_text(encoding="utf-8"))
citations = citations_from_payload(json.loads(lf.SLICE.read_text(encoding="utf-8"))["citations"])
bundle = PobCatalogProvider(
    MappingCatalogReader(world["tables"], world["rule_sources"]),
    citations=citations, release_captures=ordered, fixtures=lf.NO_FIXTURES,
    pob_commit="0" * 40, clock=lambda: "2026-10-06T00:00:00Z"
).export(ExportRequest())
results["release_order"] = {"newest_published": newer.patch_id,
                            "exported_patch": bundle.profile.patch_id}
assert bundle.profile.patch_id == older.patch_id

# Imported item requirements conflict with the normalized record.
world = lf.load_world()
cases = lf.load_cases()
items = lf.make_items(cases, world.catalog.catalog_hash)
items["ring"] = replace(items["ring"], requirements={"level": 1, "str": 1})
case = next(c for c in cases["cases"] if c["id"] == "minimal_legal_verified")
spec = {**cases["base"], "equipment": {"Ring 1": {"item": "ring"}}}
build = lf.make_build(spec, catalog_hash=world.catalog.catalog_hash)
imported = copy.deepcopy(case["imported"])
imported["items"] = {"Ring 1": {
    "name": "Invented Ring", "baseName": "Iron Ring", "rarity": "NORMAL",
    "requirements": {"level": 90, "str": 999}, "sockets": 0}}
report = LegalityValidator(catalog=world.catalog, items=items,
    imported=lf.make_imported(imported, build_hash=build.build_hash)
).validate(build, world.profile)
raw = report.to_dict()
results["item_requirements"] = {
    "record_requirements": items["ring"].requirements,
    "engine_requirements": imported["items"]["Ring 1"]["requirements"],
    "character_level": build.level,
    "character_strength": imported["strength"],
    "overall_legality": raw["legality"],
    "relevant_checks": [c for c in raw["checks"] if c["check_id"] in (
        "item_requirements", "post_import_verification")],
    "violations": raw["violations"],
}
assert not report.violations
assert next(c for c in raw["checks"] if c["check_id"] == "item_requirements")["decision"] == "legal"
print(json.dumps(results, indent=2))
