"""P04-T01: format dispatch and PoB import parsing, offline.

Inputs are the PoB-written fixtures in ``tests/fixtures/p04`` and
adversarial variations of them. The catalog is the committed slice of the
pinned catalog. No PoB, no network.
"""

from __future__ import annotations

import base64
import copy
import socket
import xml.etree.ElementTree as ET
import zlib

import pytest

import p04_fixtures as fx
from pob2opt.acquisition.content import MAX_EXPANDED_BYTES
from pob2opt.domain.codec import to_jsonable
from pob2opt.domain.enums import ParseResultStatus, RecordParseStatus
from pob2opt.domain.validation import RecordIndex, validate_record
from pob2opt.parsers import detect, parse_document
from pob2opt.parsers import formats


def code_for(xml: bytes) -> bytes:
    return base64.urlsafe_b64encode(zlib.compress(xml))


def parse(payload: bytes, **source):
    return parse_document(fx.source(payload, **source), payload, fx.context())


def mutate(name: str, change) -> bytes:
    root = ET.fromstring(fx.document_bytes(name))
    change(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


# ------------------------------------------------------------- formats ---

def test_format_is_chosen_by_signature_not_by_name():
    xml = fx.document_bytes("b01")
    assert detect(xml).format == formats.POB_XML
    assert detect(code_for(xml)).format == formats.POB_CODE
    assert detect(b"Rarity: RARE\nX\nY").format == formats.ITEM_TEXT
    assert detect(b"<!DOCTYPE html><html></html>").format == formats.SAVED_HTML
    assert detect(b'{"build": 1}').format == formats.PROVIDER_JSON


def test_a_declared_format_must_agree_with_the_bytes():
    found = detect(fx.document_bytes("b01"), declared=formats.PROVIDER_JSON)
    assert found.refused and found.reason == "declared_format_mismatch"


@pytest.mark.parametrize("payload,reason", [
    (b"", "empty_payload"),
    (b"\x00\x01\x02 not anything", "unknown_format"),
    (b"<?xml version='1.0'?><PathOfBuilding><Build/></PathOfBuilding>",
     "pob1_document"),
    (b"<?xml version='1.0'?><PathOfBuilding2><Build>", "xml_syntax"),
    (b"<?xml version='1.0'?><!DOCTYPE x [<!ENTITY a 'b'>]><PathOfBuilding2/>",
     "unsafe_xml"),
])
def test_unusable_payloads_are_refused_with_a_reason(payload, reason):
    found = detect(payload)
    assert found.refused and found.reason == reason


def test_a_valid_code_decodes_to_the_same_build_as_its_xml():
    xml = fx.document_bytes("b03")
    from_xml = parse(xml)
    from_code = parse(code_for(xml), record_id="src/code")
    assert [b.build_hash for b in from_xml.builds] == \
        [b.build_hash for b in from_code.builds]
    assert from_code.result.raw_extensions["format"] == formats.POB_CODE


def test_a_truncated_code_is_invalid_not_empty():
    code = code_for(fx.document_bytes("b03"))
    outcome = parse(code[: len(code) // 2], record_id="src/truncated")
    assert outcome.result.status is ParseResultStatus.INVALID
    assert outcome.builds == ()
    assert outcome.result.issues[0].code in ("deflate", "base64")


def test_an_expansion_past_the_cap_is_refused():
    bomb = code_for(b"<?xml version='1.0'?><PathOfBuilding2>"
                    + b" " * (MAX_EXPANDED_BYTES + 10) + b"</PathOfBuilding2>")
    assert len(bomb) < 100_000
    outcome = parse(bomb, record_id="src/bomb")
    assert outcome.result.status is ParseResultStatus.INVALID
    assert outcome.result.issues[0].code == "expanded_too_large"


def test_malformed_xml_is_invalid():
    outcome = parse(b"<?xml version='1.0'?><PathOfBuilding2><Build></Skills>",
                    record_id="src/malformed")
    assert outcome.result.status is ParseResultStatus.INVALID
    assert outcome.builds == ()


def test_an_unknown_format_is_unsupported():
    outcome = parse(b"\x89PNG\r\n\x1a\n binary", record_id="src/png")
    assert outcome.result.status is ParseResultStatus.UNSUPPORTED_FORMAT


def test_a_pob1_document_is_unsupported_not_parsed():
    outcome = parse(b"<?xml version='1.0'?><PathOfBuilding><Build "
                    b"className='Ranger'/></PathOfBuilding>",
                    record_id="src/poe1")
    assert outcome.result.status is ParseResultStatus.UNSUPPORTED_FORMAT
    assert outcome.builds == ()


# ------------------------------------------------------------ documents ---

@pytest.mark.parametrize("name", fx.COMPLETE_BUILDS)
def test_a_pob_document_parses_complete(name):
    outcome = parse(fx.document_bytes(name), record_id="src/" + name)
    assert outcome.result.status is ParseResultStatus.COMPLETE, [
        (i.code, i.field_path, i.explanation) for i in outcome.result.issues]
    (build,) = outcome.builds
    assert build.schema_version == 2
    assert build.parse_status is RecordParseStatus.COMPLETE
    assert build.raw_blob_hashes == [outcome_blob(name)]
    assert build.source_document_ids == ["src/" + name]


def outcome_blob(name):
    import hashlib
    return hashlib.sha256(fx.document_bytes(name)).hexdigest()


@pytest.mark.parametrize("name", fx.COMPLETE_BUILDS + fx.PARTIAL_BUILDS)
def test_every_record_validates_and_references_resolve(name):
    data = fx.document_bytes(name)
    outcome = parse(data, record_id="src/" + name)
    index = RecordIndex()
    index.add(fx.source(data, record_id="src/" + name))
    index.add_blob(outcome_blob(name))
    index.catalog_hashes.add(fx.slice_catalog_hash())
    for record in outcome.records:
        index.add(record)
    for record in outcome.records:
        report = validate_record(record, index=index)
        assert report.ok, (record.record_id, report.errors)


def test_parsing_is_deterministic():
    data = fx.document_bytes("b05")
    first = parse(data, record_id="src/b05")
    second = parse(data, record_id="src/b05")
    assert [to_jsonable(r) for r in first.records] == \
        [to_jsonable(r) for r in second.records]


def test_parsing_opens_no_socket(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a parser tried to open a socket")
    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    outcome = parse(fx.document_bytes("b08"), record_id="src/b08")
    assert outcome.builds


def test_issues_carry_field_paths_and_locators():
    outcome = parse(fx.document_bytes("b02"), record_id="src/b02")
    assert outcome.result.status is ParseResultStatus.PARTIAL
    for issue in outcome.result.issues:
        assert issue.field_path.startswith("/")
        assert issue.source_locator
        assert issue.explanation


# -------------------------------------------------------------- variants ---

def test_each_variant_has_its_own_build_linked_to_the_shared_guide():
    data = fx.document_bytes("variants")
    outcome = parse(data, record_id="src/guide")
    assert len(outcome.builds) == 2
    labels = sorted(v.label for v in outcome.split.variants)
    assert labels == ["Endgame {2}", "Leveling {1}"]
    first, second = outcome.builds
    assert first.variant_id != second.variant_id
    assert first.build_hash != second.build_hash
    assert first.raw_blob_hashes == second.raw_blob_hashes == [
        __import__("hashlib").sha256(data).hexdigest()]
    assert first.source_document_ids == second.source_document_ids == [
        "src/guide"]
    assert all(b.parse_status is RecordParseStatus.COMPLETE
               for b in outcome.builds)


def test_the_leveling_tree_is_not_paired_with_endgame_gear():
    outcome = parse(fx.document_bytes("variants"), record_id="src/guide")
    by_label = {v.label: v for v in outcome.split.variants}
    leveling = by_label["Leveling {1}"].selection
    endgame = by_label["Endgame {2}"].selection
    for tag in ("Tree", "Skills", "Items", "Config"):
        assert leveling[tag] != endgame[tag], tag


def test_a_set_no_loadout_links_is_reported_and_not_merged():
    outcome = parse(fx.document_bytes("variants"), record_id="src/guide")
    codes = [i.code for i in outcome.result.issues]
    assert codes == ["unlinked_variant_set"]
    assert outcome.result.status is ParseResultStatus.PARTIAL
    unlinked = outcome.result.raw_extensions["unlinked_sets"]
    assert len(unlinked) == 1 and "Unlinked trade test" in unlinked[0]["reason"]


def test_a_single_set_document_is_one_variant():
    outcome = parse(fx.document_bytes("b01"), record_id="src/b01")
    assert len(outcome.split.variants) == 1
    assert outcome.split.variants[0].is_active


def test_ambiguous_loadout_titles_form_no_variant():
    def duplicate(root):
        items = root.find("Items")
        twin = copy.deepcopy(items.find("ItemSet[@id='2']"))
        twin.set("id", "4")
        items.append(twin)
    outcome = parse(mutate("variants", duplicate), record_id="src/amb")
    assert len(outcome.builds) == 1  # the active selection only
    reasons = " ".join(i.explanation for i in outcome.result.issues)
    assert "ambiguous" in reasons


# ------------------------------------------------------ missing content ---

@pytest.mark.parametrize("section,code", [
    ("Tree", "missing_tree"),
    ("Items", "missing_items"),
    ("Skills", "missing_skills"),
])
def test_a_missing_section_is_unknown_not_empty(section, code):
    payload = mutate("b01", lambda root: root.remove(root.find(section)))
    outcome = parse(payload, record_id="src/missing")
    assert outcome.result.status is ParseResultStatus.PARTIAL
    assert code in [i.code for i in outcome.result.issues]
    (build,) = outcome.builds
    assert build.parse_status is RecordParseStatus.PARTIAL


def test_a_missing_passive_tree_blocks_legal_evaluation():
    payload = mutate("b01", lambda root: root.remove(root.find("Tree")))
    (build,) = parse(payload, record_id="src/notree").builds
    assert any(r.field_path == "/passives" for r in build.unresolved_refs)
    assert build.parse_status is not RecordParseStatus.COMPLETE


def test_a_layout_change_is_a_recognizable_failure():
    payload = mutate("b01", lambda root: root.remove(root.find("Build")))
    outcome = parse(payload, record_id="src/layout")
    assert outcome.result.status is ParseResultStatus.INVALID
    assert outcome.result.issues[0].code == "layout_unrecognized"
    assert outcome.builds == () and outcome.items == ()


def test_an_unknown_class_produces_no_build():
    payload = mutate("b01", lambda root: root.find("Build").set(
        "className", "Templar"))
    outcome = parse(payload, record_id="src/class")
    assert outcome.builds == ()
    assert "unresolved_class" in [i.code for i in outcome.result.issues]


def test_unknown_top_level_elements_are_kept_in_raw_extensions():
    def add(root):
        ET.SubElement(root, "FutureSection", {"x": "1"})
    outcome = parse(mutate("b01", add), record_id="src/future")
    assert "FutureSection" in outcome.result.raw_extensions["unknown_elements"]


def test_coverage_is_counted_by_domain():
    outcome = parse(fx.document_bytes("b04"), record_id="src/b04")
    domains = {c.domain: c for c in outcome.result.field_coverage}
    for name in ("class", "passives", "equipment", "skills", "supports",
                 "config", "item_affixes"):
        assert name in domains
        assert domains[name].resolved <= domains[name].present
    assert domains["supports"].present == 3
