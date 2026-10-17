"""P04-T02: source parsers, offline.

D02 has approved no provider representation, so the only build-data parser
is the PoB one, reached through local files and sharing codes. Provider
pages and JSON exports must come back as ``provider_parser_blocked``, never
as a build; a guide page still yields unverified claims from its prose.

The required per-parser fixtures, for the PoB representation: complete build
(``test_p04_t01_parse``), missing gear, multiple variants (``test_p04_t01``),
old patch, renamed or unknown entity, layout change (``test_p04_t01``) and
absent popularity.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

import p04_fixtures as fx
from pob2opt.domain.enums import ParseResultStatus, RecordParseStatus
from pob2opt.domain.records import PopularitySignal
from pob2opt.parsers import parse_document, visible_text
from pob2opt.parsers.dispatch import BLOCKED_PROVIDERS


def parse(payload, **source):
    return parse_document(fx.source(payload, **source), payload, fx.context())


def mutate(name, change):
    root = ET.fromstring(fx.document_bytes(name))
    change(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


GUIDE = b"""<!DOCTYPE html><html><head><title>Lightning Arrow Deadeye</title>
<script>window.build = {"items": []}; fetch("https://x.invalid/")</script>
<style>p{color:red}</style></head><body>
<h1>Lightning Arrow Deadeye</h1>
<h2>Skills</h2>
<p>Use Lightning Arrow with Martial Tempo. Supports: Lightning Arrow, Fork.</p>
</body></html>"""


@pytest.mark.parametrize("provider", BLOCKED_PROVIDERS)
def test_a_provider_page_is_blocked_and_yields_no_build(provider):
    outcome = parse(GUIDE, provider=provider, media_type="text/html",
                    record_id="src/" + provider)
    assert outcome.builds == () and outcome.items == ()
    assert outcome.result.status is ParseResultStatus.PARTIAL
    (issue,) = outcome.result.issues
    assert issue.code == "provider_parser_blocked"
    assert "D02" in issue.explanation


def test_a_title_and_skill_names_are_not_a_build():
    outcome = parse(GUIDE, provider="mobalytics", media_type="text/html")
    assert outcome.result.status is not ParseResultStatus.COMPLETE
    assert outcome.builds == ()


def test_a_saved_page_keeps_visible_text_and_drops_scripts():
    text = visible_text(GUIDE.decode("utf-8"))
    assert "Use Lightning Arrow with Martial Tempo." in text
    assert "fetch" not in text and "color:red" not in text


@pytest.mark.parametrize("provider", BLOCKED_PROVIDERS)
def test_a_provider_json_export_is_unsupported(provider):
    outcome = parse(b'{"build": {"class": "Ranger", "skills": ["Arc"]}}',
                    provider=provider, media_type="application/json")
    assert outcome.result.status is ParseResultStatus.UNSUPPORTED_FORMAT
    assert outcome.result.issues[0].code == "provider_parser_blocked"
    assert outcome.builds == ()


def test_missing_gear_is_unknown_equipment():
    payload = mutate("b04", lambda root: root.remove(root.find("Items")))
    outcome = parse(payload)
    (build,) = outcome.builds
    assert build.equipment == {}
    assert build.parse_status is RecordParseStatus.PARTIAL
    assert "missing_items" in [i.code for i in outcome.result.issues]


def test_an_empty_slot_is_empty_not_missing():
    outcome = parse(fx.document_bytes("b07"))
    (build,) = outcome.builds
    empties = [slot for slot, content in build.equipment.items()
               if content is None]
    assert empties  # explicitly empty slots are null, not dropped
    assert build.parse_status is RecordParseStatus.COMPLETE


def test_an_old_tree_version_is_named():
    payload = mutate("b01", lambda root: root.find("Tree/Spec").set(
        "treeVersion", "0_1"))
    outcome = parse(payload)
    issue = next(i for i in outcome.result.issues
                 if i.code == "old_tree_version")
    assert "0_1" in issue.explanation
    assert outcome.result.raw_extensions["tree_version"] == "0_1"


def test_a_declared_patch_is_kept_as_a_declaration():
    outcome = parse(fx.document_bytes("b01"), declared_patch="0.3.1")
    (build,) = outcome.builds
    assert build.declared_patch == "0.3.1"


def test_an_unknown_entity_is_unresolved_and_kept():
    def rename(root):
        gem = root.find("Skills/SkillSet/Skill/Gem")
        gem.set("skillId", "RenamedInAFuturePatchPlayer")
    outcome = parse(mutate("b01", rename))
    (build,) = outcome.builds
    assert build.parse_status is RecordParseStatus.PARTIAL
    references = [r.reference for r in build.unresolved_refs]
    assert "RenamedInAFuturePatchPlayer" in references


def test_an_unknown_passive_is_unresolved_not_dropped_silently():
    def stale(root):
        spec = root.find("Tree/Spec")
        spec.set("nodes", spec.get("nodes") + ",999999")
    outcome = parse(mutate("b01", stale))
    (build,) = outcome.builds
    assert build.parse_status is RecordParseStatus.PARTIAL
    assert "999999" in [r.reference for r in build.unresolved_refs]
    passives = {c.domain: c for c in outcome.result.field_coverage}["passives"]
    assert passives.missing == 1


def test_absent_popularity_stays_absent():
    document = fx.source(fx.document_bytes("b01"))
    assert document.popularity == []
    outcome = parse_document(document, fx.document_bytes("b01"), fx.context())
    assert "popularity" not in outcome.result.raw_extensions
    assert outcome.result.status is ParseResultStatus.COMPLETE


def test_popularity_does_not_change_a_parse():
    plain = parse(fx.document_bytes("b01"))
    popular = parse(fx.document_bytes("b01"), popularity=[
        PopularitySignal(kind="favourites", value=99999.0,
                         observed_at=fx.CREATED_AT)])
    assert [b.build_hash for b in plain.builds] == \
        [b.build_hash for b in popular.builds]
    assert plain.result.status is popular.result.status


def test_structured_data_beats_display_labels():
    """A group label naming another skill does not change the skill."""
    def relabel(root):
        root.find("Skills/SkillSet/Skill").set("label", "Lightning Arrow")
    plain = parse(fx.document_bytes("b01")).builds[0]
    relabelled = parse(mutate("b01", relabel)).builds[0]
    assert plain.build_hash == relabelled.build_hash
    assert relabelled.skill_groups[0].group_id == "Lightning Arrow"
