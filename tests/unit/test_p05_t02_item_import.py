"""P05-T02: item text and market capture import. Offline, synthetic fixtures.

Acceptance cases from https://github.com/kaporli/pob2-tools/issues/29, by test name:

* same-name different-roll items remain distinct:
  ``test_acceptance_same_name_different_roll_items_remain_distinct``;
* equal-stat separate listings can both exist:
  ``test_acceptance_equal_stat_separate_listings_both_exist``;
* a high-price non-exalted listing survives import:
  ``test_acceptance_high_price_non_exalted_listing_survives``;
* missing price is not zero: ``test_acceptance_missing_price_is_null_not_zero``;
* modifier categories round trip without silent loss:
  ``test_acceptance_every_category_round_trips_without_loss`` and
  ``test_acceptance_attribute_requirements_are_reported_not_dropped``
  (the engine lane is ``tests/engine/test_p05_t02_item_conversion.py``).

The capture is acceptance-examples.md example 5.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import replace

import pytest

import p05_fixtures as fx
from pob2opt import cli
from pob2opt.domain.enums import (Availability, ModifierCategory,
                                  ModifierParseStatus, ParseResultStatus,
                                  RecordParseStatus)
from pob2opt.domain.identity import item_identity
from pob2opt.domain.validation import validate_record
from pob2opt.evaluation import export_item, import_item
from pob2opt.evaluation.roundtrip import diff_identity
from pob2opt.market import capture as capture_module
from pob2opt.market import importer as importer_module
from pob2opt.market.importer import (import_market, item_availability,
                                     listing_key)
from pob2opt.parsers import formats
from pob2opt.parsers.dispatch import parse_document, read_item_text
from pob2opt.parsers.resolve import naming_from_catalog
from pob2opt.storage import RunStore


def read(name: str):
    text = fx.game_items()[name]
    out = read_item_text(text, fx.document(text.encode(), media_type="text/plain"),
                         fx.context(), record_id="r")
    assert out.item is not None, (name, out.refused, out.issues)
    return out


def example5(data=None, existing=lambda _id: None):
    payload = fx.capture_bytes(data)
    return import_market(fx.document(payload), payload, fx.context(),
                         existing=existing)


def by_listing(result):
    return {listing.listing_id.rsplit("/", 1)[1]: listing
            for listing in result.listings}


@pytest.mark.parametrize("ending", ["", "\n--------\nNote: fixture"])
@pytest.mark.parametrize("modifier", ["+21 to Dexterity", "+21 to Dexterity (crafted)"])
def test_unterminated_reminder_refuses_the_item_and_capture(ending, modifier):
    text = fx.game_items()["ring_shared_name_a"].replace(
        "+21 to Dexterity", "(unterminated reminder\n" + modifier) + ending
    out = read_item_text(text, fx.document(text.encode(), media_type="text/plain"),
                         fx.context(), record_id="bad-reminder")
    assert out.item is None
    assert out.refused.reason == "unterminated_reminder"
    data = fx.capture_data()
    data["entries"][0]["item_text"] = text
    result = example5(data)
    assert result.result.status is ParseResultStatus.INVALID
    assert not result.items and not result.listings


@pytest.mark.parametrize("reminder", ["(valid reminder)", "(valid reminder\non two lines)",
                                      "(valid (nested)\nreminder)"])
def test_closed_reminder_preserves_following_modifiers(reminder):
    text = fx.game_items()["ring_shared_name_a"].replace(
        "+21 to Dexterity", reminder + "\n+21 to Dexterity")
    out = read_item_text(text, fx.document(text.encode(), media_type="text/plain"),
                         fx.context(), record_id="closed-reminder")
    assert out.status is ParseResultStatus.COMPLETE
    assert out.item.item_hash == read("ring_shared_name_a").item.item_hash
    assert any(m.text == "+21 to Dexterity" for m in out.item.modifiers)


def capture_with_timestamp(location, timestamp):
    data = fx.capture_data()
    if location == "capture":
        data["observed_at"] = timestamp
    else:
        data["entries"][0]["listing"][location] = timestamp
    return data


@pytest.mark.parametrize("location", ["capture", "observed_at", "listed_at"])
@pytest.mark.parametrize("timestamp", [
    "2026-02-30T18:00:00Z", "2026-13-16T25:00:00Z", "2025-02-29T18:00:00Z",
    "2026-10-16T24:00:00Z", "2026-10-16T18:60:00Z", "2026-10-16T18:00:00Z\n",
])
def test_impossible_capture_dates_are_invalid(location, timestamp):
    data = capture_with_timestamp(location, timestamp)
    capture, issues = capture_module.read_capture(json.dumps(data))
    assert capture is None
    path = "/observed_at" if location == "capture" else "/entries/0/listing/" + location
    assert any(i.code == "invalid_timestamp" and i.field_path == path for i in issues)
    result = example5(data)
    assert result.result.status is ParseResultStatus.INVALID
    assert not result.items and not result.listings


@pytest.mark.parametrize("location", ["capture", "observed_at", "listed_at"])
@pytest.mark.parametrize("timestamp", ["2024-02-29T23:59:59Z", "2026-10-16T18:00:00.123456Z"])
def test_valid_capture_dates_preserve_source_value(location, timestamp):
    data = capture_with_timestamp(location, timestamp)
    capture, issues = capture_module.read_capture(json.dumps(data))
    assert not issues
    value = capture.observed_at if location == "capture" else getattr(capture.entries[0].listing, location)
    assert value == timestamp
    assert example5(data).result.status is ParseResultStatus.COMPLETE


@pytest.mark.parametrize("location", ["capture", "observed_at", "listed_at"])
def test_cli_rejects_impossible_dates_without_storing_listings(location, tmp_path, bundle, capsys):
    path = tmp_path / "capture.json"
    path.write_bytes(fx.capture_bytes(capture_with_timestamp(location, "2026-02-30T18:00:00Z")))
    corpus = tmp_path / "corpus"
    code, report = run_import(path, corpus, bundle, capsys)
    assert code == 2 and report["status"] == "invalid"
    with RunStore.open_corpus(corpus) as store:
        assert not list(store.iter_normalized("listing"))
        assert not list(store.iter_normalized("item_instance"))


# ---------------------------------------------------------- acceptance ===

def test_acceptance_same_name_different_roll_items_remain_distinct():
    a, b = read("ring_shared_name_a").item, read("ring_shared_name_b").item
    assert a.display_name == b.display_name == "Shared Name"
    assert a.item_hash != b.item_hash
    listings = by_listing(example5())
    assert listings["L1"].item_hash != listings["L2"].item_hash


def test_acceptance_equal_stat_separate_listings_both_exist():
    result = example5()
    listings = by_listing(result)
    assert listings["L2"].item_hash == listings["L3"].item_hash
    assert listings["L2"].listing_id != listings["L3"].listing_id
    # One item record for the shared stats, two listings pointing at it.
    hashes = [item.item_hash for item in result.items]
    assert hashes.count(listings["L2"].item_hash) == 1
    assert len(result.listings) == 3


def test_acceptance_high_price_non_exalted_listing_survives():
    listing = by_listing(example5())["L2"]
    assert (listing.price_amount, listing.price_currency) == ("1000", "divine")
    assert validate_record(listing).ok


def test_acceptance_missing_price_is_null_not_zero():
    listing = by_listing(example5())["L3"]
    assert listing.price_amount is None and listing.price_currency is None
    data = fx.capture_data()
    data["entries"][2]["listing"]["price"] = {"amount": "0",
                                              "currency": "exalted"}
    free = by_listing(example5(data))["L3"]
    assert free.price_amount == "0"
    assert free != listing


def test_acceptance_every_category_round_trips_without_loss():
    """Game text -> record -> PoB item text -> record keeps the identity."""
    source = read("bow_every_category").item
    assert source.parse_status is RecordParseStatus.COMPLETE
    assert {m.category for m in source.modifiers} == {
        ModifierCategory.ENCHANT, ModifierCategory.RUNE,
        ModifierCategory.IMPLICIT, ModifierCategory.EXPLICIT,
        ModifierCategory.FRACTURED, ModifierCategory.CRAFTED,
        ModifierCategory.DESECRATED}
    naming = naming_from_catalog(fx.context().entities).naming
    text, losses = export_item(source, naming)
    report = losses.report()
    assert report.completeness == "complete", report.as_dict()
    restored = import_item(text, naming, record_id="back",
                           created_at=fx.context().created_at,
                           catalog_hash=source.catalog_hash)
    assert diff_identity(item_identity(source), item_identity(restored)) == []
    assert restored.item_hash == source.item_hash


def test_acceptance_attribute_requirements_are_reported_not_dropped():
    """PoB item text carries only the level requirement; the rest is named."""
    source = read("spear_attribute_requirements").item
    assert source.requirements == {"level": 59, "str": 33, "dex": 81}
    naming = naming_from_catalog(fx.context().entities).naming
    _text, losses = export_item(source, naming)
    lost = {u.field_path: u for u in losses.report().unsupported}
    assert lost["/requirements/str"].preserved == 33
    assert lost["/requirements/dex"].preserved == 81
    assert lost["/requirements/str"].affects_identity


# -------------------------------------------------- game text fidelity ===

def test_game_text_keeps_base_rarity_quality_sockets_flags_and_raw_text():
    item = read("bow_every_category").item
    assert (item.base_id, item.rarity, item.item_level) == (
        "poe2/item_bases/Crude Bow", "rare", 82)
    assert item.properties == {"quality": 20}
    assert [s.colour for s in item.sockets] == ["S", "S"]
    assert item.flags == {"mirrored": True}
    assert item.raw_text == fx.game_items()["bow_every_category"]
    crafted = [m for m in item.modifiers
               if m.category is ModifierCategory.CRAFTED][0]
    assert crafted.flags == {"unscalable": True}


def test_displayed_totals_are_not_stored_as_base_properties():
    item = read("spear_attribute_requirements").item
    assert "Physical Damage" in item.raw_text
    assert item.properties == {}


def test_grants_skill_lines_are_implicit_as_pob_reads_them():
    item = read("spear_attribute_requirements").item
    grants = [m for m in item.modifiers if m.text.startswith("Grants Skill")]
    assert [m.category for m in grants] == [ModifierCategory.IMPLICIT]


def test_a_seller_note_is_not_part_of_the_item():
    plain = read("ring_shared_name_a")
    noted = read("ring_shared_name_a_with_note")
    assert plain.item.item_hash == noted.item.item_hash
    assert "Note:" in noted.item.raw_text
    assert [i.code for i in noted.issues] == ["price_note_not_item_data"]
    assert noted.status is ParseResultStatus.COMPLETE


def test_unplaced_lines_stay_unknown_and_make_the_item_partial():
    out = read("unique_with_flavour_text")
    unknown = [m for m in out.item.modifiers
               if m.category is ModifierCategory.UNKNOWN]
    assert [m.text for m in unknown] == ["FIXTURE flavour text, first line",
                                         "and its second line"]
    assert all(m.parse_status is ModifierParseStatus.UNRESOLVED
               for m in unknown)
    assert out.item.parse_status is RecordParseStatus.PARTIAL
    assert out.item.requirements == {"level": 30, "dex": 40}


def test_a_magic_name_resolves_its_base_by_the_longest_contained_name():
    assert read("magic_ring").item.base_id == "poe2/item_bases/Iron Ring"


def test_advanced_copy_is_refused_not_guessed():
    text = fx.game_items()["advanced_copy"]
    out = read_item_text(text, fx.document(text.encode()), fx.context(),
                         record_id="r")
    assert out.item is None
    assert out.refused.reason == "advanced_copy_unsupported"


def test_the_parse_command_reads_game_text_too():
    text = fx.game_items()["ring_shared_name_b"].encode()
    outcome = parse_document(fx.document(text, media_type="text/plain"),
                             text, fx.context())
    assert outcome.result.status is ParseResultStatus.COMPLETE
    assert outcome.items[0].base_id == "poe2/item_bases/Iron Ring"


def test_pob_item_text_still_imports_through_the_same_path():
    text = "\n".join(["Rarity: RARE", "FIXTURE PoB Ring", "Iron Ring",
                      "Item Level: 79", "Implicits: 1",
                      "Adds 1 to 4 Physical Damage to Attacks",
                      "+21 to Dexterity"])
    result = import_market(fx.document(text.encode()), text.encode(),
                           fx.context())
    assert result.result.status is ParseResultStatus.COMPLETE
    assert result.items[0].base_id == "poe2/item_bases/Iron Ring"


def pob_text(*rune_lines):
    return "\n".join(["Rarity: RARE", "FIXTURE PoB Bow", "Crude Bow",
                      "Item Level: 82", "Sockets: S S", *rune_lines,
                      "Implicits: 1",
                      "{enchant}{rune}FIXTUREMOD 16% increased Physical Damage",
                      "+21 to Dexterity"])


def test_pob_rune_socket_lines_are_rune_names_not_modifiers():
    naming = naming_from_catalog(fx.context().entities).naming
    item = import_item(pob_text("Rune: None", "Rune: Iron Rune"), naming,
                       record_id="r", created_at=fx.context().created_at,
                       catalog_hash="c" * 64)
    assert item.properties["runes"] == ["None", "Iron Rune"]
    assert [(m.category, m.flags) for m in item.modifiers] == [
        (ModifierCategory.RUNE, {}), (ModifierCategory.EXPLICIT, {})]
    text, losses = export_item(item, naming)
    assert losses.report().completeness == "complete"
    back = import_item(text, naming, record_id="b",
                       created_at=fx.context().created_at,
                       catalog_hash="c" * 64)
    assert back.item_hash == item.item_hash


def test_empty_rune_sockets_add_nothing_to_the_item():
    naming = naming_from_catalog(fx.context().entities).naming
    empty = import_item(pob_text("Rune: None", "Rune: None"), naming,
                        record_id="r", created_at=fx.context().created_at,
                        catalog_hash="c" * 64)
    bare = import_item(pob_text(), naming, record_id="r",
                       created_at=fx.context().created_at,
                       catalog_hash="c" * 64)
    assert "runes" not in empty.properties
    assert empty.item_hash == bare.item_hash


def test_a_magic_pob_item_resolves_its_base_from_its_name():
    naming = naming_from_catalog(fx.context().entities).naming
    item = import_item("Rarity: MAGIC\nIron Ring of the Fixture\nImplicits: 0\n"
                       "+13 to Dexterity", naming, record_id="r",
                       created_at=fx.context().created_at,
                       catalog_hash="c" * 64)
    assert item.base_id == "poe2/item_bases/Iron Ring"


# ------------------------------------------------- identity and dedup ===

def test_items_deduplicate_by_canonical_stats_never_display_name():
    b = read("ring_shared_name_b").item
    other = read("ring_other_name_same_stats_as_b").item
    assert b.display_name != other.display_name
    assert b.item_hash == other.item_hash


def test_listings_deduplicate_by_provider_realm_league_and_listing_id():
    data = fx.capture_data()
    data["entries"].append(dict(data["entries"][0]))  # L1 seen twice
    result = example5(data)
    assert [o.listing_state for o in result.entries][-1] == "reused"
    assert len(result.listings) == 3
    assert listing_key("p", "poe2", "League A", "L1") != listing_key(
        "p", "poe2", "League B", "L1")
    assert listing_key("a/b", "poe2", "x", "1") != listing_key(
        "a", "b/poe2", "x", "1")


def test_one_listing_with_two_contents_in_one_file_is_invalid():
    data = fx.capture_data()
    clash = json.loads(json.dumps(data["entries"][0]))
    clash["listing"]["price"] = {"amount": "6", "currency": "exalted"}
    data["entries"].append(clash)
    result = example5(data)
    assert result.result.status is ParseResultStatus.INVALID
    assert "conflicting_listing" in {i.code for i in result.result.issues}
    assert result.items == () and result.listings == ()


def test_a_stored_listing_is_never_overwritten_by_a_new_observation():
    first = example5()
    stored = {l.listing_id: l for l in first.listings}
    data = fx.capture_data()
    data["entries"][0]["listing"]["price"] = {"amount": "4",
                                              "currency": "exalted"}
    second = example5(data, existing=stored.get)
    assert second.result.status is ParseResultStatus.PARTIAL
    assert "listing_conflict" in {i.code for i in second.result.issues}
    assert second.listings == ()  # L2 and L3 identical, L1 conflicted
    assert [o.listing_state for o in second.entries[:3]] == [
        "conflict", "reused", "reused"]


def test_an_item_without_listing_evidence_has_unknown_availability():
    result = example5()
    magic = result.entries[3]
    assert magic.listing_id is None
    assert item_availability([l for l in result.listings
                              if l.item_hash == magic.item_hash]) == "unknown"
    l1 = by_listing(result)["L1"]
    assert l1.availability is Availability.OBSERVED
    assert item_availability([l1]) == "observed"


def test_listing_fields_are_the_observation_and_nothing_more():
    l1 = by_listing(example5())["L1"]
    assert (l1.provider, l1.realm, l1.league_id) == (
        "fixture-market", "poe2", "Fixture League")
    assert l1.observed_at == l1.last_checked_at == "2026-10-16T18:00:00Z"
    assert l1.quantity == 1 and l1.listed_at is None
    assert by_listing(example5())["L3"].quantity is None


# ------------------------------------------------ price is not filtered ===

def test_no_currency_or_amount_is_rejected_for_being_unusual():
    data = fx.capture_data()
    data["entries"][0]["listing"]["price"] = {
        "amount": "123456789012345678901234567890.5", "currency": "mirror"}
    listing = by_listing(example5(data))["L1"]
    assert listing.price_amount == "123456789012345678901234567890.5"
    assert listing.price_currency == "mirror"


def test_the_importer_has_no_price_cap_or_exalted_assumption():
    for module in (importer_module, capture_module):
        source = inspect.getsource(module).lower()
        assert "exalted" not in source
        assert "price_cap" not in source and "budget" not in source


@pytest.mark.parametrize("price, code", [
    ({"amount": 1000, "currency": "divine"}, "price_not_decimal_string"),
    ({"amount": "-5", "currency": "divine"}, "price_not_decimal_string"),
    ({"amount": "", "currency": "divine"}, "price_not_decimal_string"),
    ({"amount": "5"}, "missing_field"),
])
def test_a_price_that_cannot_be_read_exactly_is_refused(price, code):
    data = fx.capture_data()
    data["entries"][0]["listing"]["price"] = price
    result = example5(data)
    assert result.result.status is ParseResultStatus.INVALID
    assert code in {i.code for i in result.result.issues}


def test_a_listing_record_needs_a_currency_for_its_amount():
    l1 = by_listing(example5())["L1"]
    report = validate_record(replace(l1, price_currency=None))
    assert "price_without_currency" in {e.code for e in report.errors}
    report = validate_record(replace(l1, price_amount="-1"))
    assert "negative_price" in {e.code for e in report.errors}


# ------------------------------------------------------- refusals ===

def test_a_provider_export_is_refused_naming_d01():
    payload = json.dumps({"result": [{"id": "x", "item": {}}]}).encode()
    result = import_market(fx.document(payload), payload, fx.context())
    assert result.result.status is ParseResultStatus.UNSUPPORTED_FORMAT
    issue = result.result.issues[0]
    assert issue.code == "provider_export_blocked"
    assert "D01" in issue.explanation


def test_the_parse_command_does_not_read_a_capture():
    payload = fx.capture_bytes()
    assert formats.detect(payload).format == formats.MARKET_CAPTURE
    outcome = parse_document(fx.document(payload), payload, fx.context())
    assert outcome.result.status is ParseResultStatus.UNSUPPORTED_FORMAT


def test_unknown_capture_keys_are_named_not_interpreted():
    result = example5()
    assert set(result.result.raw_extensions["unknown_fields"]) == {
        "/kind", "/purpose", "/not_a_claim"}


def test_one_unreadable_item_text_makes_the_whole_file_invalid():
    data = fx.capture_data()
    data["entries"][1]["item_text"] = fx.game_items()["advanced_copy"]
    result = example5(data)
    assert result.result.status is ParseResultStatus.INVALID
    assert result.records == [result.result]


# --------------------------------------------------------------- CLI ===

@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    return fx.export_bundle(tmp_path_factory.mktemp("p05catalog"))


def run_import(path, corpus, bundle, capsys):
    code = cli.main(["market", "import", "--input", str(path), "--corpus",
                     str(corpus), "--catalog", str(bundle)])
    out = capsys.readouterr().out
    return code, json.loads(out)


def test_cli_stores_items_and_listings_that_resolve(tmp_path, bundle, capsys):
    path = tmp_path / "capture.json"
    path.write_bytes(fx.capture_bytes())
    corpus = tmp_path / "corpus"
    code, report = run_import(path, corpus, bundle, capsys)
    assert code == 0, report
    assert report["status"] == "complete"
    assert len(report["listings"]) == 3 and len(report["items"]) == 3
    availability = {i["display_name"]: i["availability"]
                    for i in report["items"]}
    assert availability["Iron Ring of the Fixture"] == "unknown"
    with RunStore.open_corpus(corpus) as store:
        assert store.unresolved_references() == {}
        document = store.get_source(report["source_document_id"])
        assert document.access_method.value == "manual_capture"
        assert len(list(store.iter_normalized("listing"))) == 3

    again, second = run_import(path, corpus, bundle, capsys)
    assert again == 0 and second["unchanged"] is True


def test_cli_item_text_is_a_local_file_with_unknown_availability(
        tmp_path, bundle, capsys):
    path = tmp_path / "ring.txt"
    path.write_text(fx.game_items()["ring_shared_name_a"], encoding="utf-8")
    code, report = run_import(path, tmp_path / "corpus", bundle, capsys)
    assert code == 0, report
    assert report["listings"] == []
    assert [i["availability"] for i in report["items"]] == ["unknown"]
    with RunStore.open_corpus(tmp_path / "corpus") as store:
        document = store.get_source(report["source_document_id"])
        assert document.access_method.value == "local_file"


def test_cli_a_second_capture_reuses_the_stored_item(tmp_path, bundle, capsys):
    corpus = tmp_path / "corpus"
    first = tmp_path / "a.txt"
    first.write_text(fx.game_items()["ring_shared_name_b"], encoding="utf-8")
    run_import(first, corpus, bundle, capsys)
    path = tmp_path / "capture.json"
    path.write_bytes(fx.capture_bytes())
    code, report = run_import(path, corpus, bundle, capsys)
    assert code == 0
    with RunStore.open_corpus(corpus) as store:
        items = list(store.iter_normalized("item_instance"))
        hashes = [i.item_hash for i in items]
        assert len(hashes) == len(set(hashes)) == 3


def test_cli_exit_codes_for_invalid_and_blocked_input(tmp_path, bundle, capsys):
    data = fx.capture_data()
    data["entries"][0]["listing"]["price"] = {"amount": 5, "currency": "x"}
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(data), encoding="utf-8")
    code, report = run_import(bad, tmp_path / "c1", bundle, capsys)
    assert code == 2 and report["status"] == "invalid"
    provider = tmp_path / "provider.json"
    provider.write_text(json.dumps({"result": []}), encoding="utf-8")
    code, report = run_import(provider, tmp_path / "c2", bundle, capsys)
    assert code == 3 and report["status"] == "unsupported_format"


def test_cli_without_a_catalog_bundle_is_blocked(tmp_path, capsys):
    path = tmp_path / "ring.txt"
    path.write_text(fx.game_items()["ring_shared_name_a"], encoding="utf-8")
    code = cli.main(["market", "import", "--input", str(path), "--corpus",
                     str(tmp_path / "c"), "--catalog", str(tmp_path / "none")])
    assert code == 3
    capsys.readouterr()
