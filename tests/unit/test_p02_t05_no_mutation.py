"""P02-T05: parsing and conversion must not mutate the source object.

The task states it as a requirement, and the F12 characterization showed why:
``convert_trade_item`` used to write seven default arrays back into the item
object it was handed, so a caller's record changed as a side effect of being
converted. The Python side is checked here against the canonical JSON of the
whole input, not against a shallow copy, so a nested list or dict mutated in
place is caught too. The Lua side is checked in
``tests/engine/test_f12_item_conversion_golden.py`` and
``tests/integration/test_f12_item_conversion_luajit.py``.

Offline only.
"""

from __future__ import annotations

import pytest
from p02_t05_fixtures import (CATALOG_HASH, CREATED_AT, SYNTHETIC_NAMING,
                              every_category_weapon, item_granted_group_build,
                              progression_build, resolved_modifier_item,
                              supported_build, trigger_nested_build,
                              unresolved_catalog_build, variant_helmet)

from pob2opt.domain.codec import to_jsonable
from pob2opt.domain.identity import canonical_text
from pob2opt.evaluation import (export_build, export_item, import_build,
                                import_item, round_trip)
from pob2opt.evaluation.roundtrip import SourceMutated

BUILDS = {
    "supported": supported_build,
    "trigger_nested": trigger_nested_build,
    "progression": progression_build,
    "item_granted_group": item_granted_group_build,
    "unresolved_catalog": unresolved_catalog_build,
}
ITEMS = {
    "every_category_weapon": every_category_weapon,
    "variant_helmet": variant_helmet,
    "resolved_modifier": resolved_modifier_item,
}


def fingerprint(value) -> str:
    return canonical_text(to_jsonable(value))


@pytest.mark.parametrize("name", sorted(BUILDS))
def test_exporting_a_build_does_not_change_it(name):
    build, items = BUILDS[name]()
    before_build = fingerprint(build)
    before_items = {k: fingerprint(v) for k, v in items.items()}
    export_build(build, items, SYNTHETIC_NAMING)
    assert fingerprint(build) == before_build
    assert {k: fingerprint(v) for k, v in items.items()} == before_items


@pytest.mark.parametrize("name", sorted(ITEMS))
def test_exporting_an_item_does_not_change_it(name):
    source = ITEMS[name]()
    before = fingerprint(source)
    export_item(source, SYNTHETIC_NAMING)
    assert fingerprint(source) == before


def test_the_naming_table_is_not_changed_by_a_conversion():
    before = fingerprint({
        "class_names": dict(SYNTHETIC_NAMING.class_names),
        "node_ids": dict(SYNTHETIC_NAMING.node_ids),
        "slot_names": dict(SYNTHETIC_NAMING.slot_names),
        "skill_ids": dict(SYNTHETIC_NAMING.skill_ids),
    })
    build, items = supported_build()
    export = export_build(build, items, SYNTHETIC_NAMING)
    import_build(export.xml, SYNTHETIC_NAMING, record_id="r",
                 created_at=CREATED_AT, catalog_hash=CATALOG_HASH)
    assert fingerprint({
        "class_names": dict(SYNTHETIC_NAMING.class_names),
        "node_ids": dict(SYNTHETIC_NAMING.node_ids),
        "slot_names": dict(SYNTHETIC_NAMING.slot_names),
        "skill_ids": dict(SYNTHETIC_NAMING.skill_ids),
    }) == before


def test_the_items_mapping_handed_to_the_export_is_not_extended():
    build, items = supported_build()
    keys = sorted(items)
    export_build(build, items, SYNTHETIC_NAMING)
    assert sorted(items) == keys


def test_importing_twice_from_one_document_gives_the_same_record():
    build, items = supported_build()
    export = export_build(build, items, SYNTHETIC_NAMING)
    first = import_build(export.xml, SYNTHETIC_NAMING, record_id="r",
                         created_at=CREATED_AT, catalog_hash=CATALOG_HASH)
    second = import_build(export.xml, SYNTHETIC_NAMING, record_id="r",
                          created_at=CREATED_AT, catalog_hash=CATALOG_HASH)
    assert first.build.build_hash == second.build.build_hash
    assert sorted(first.items) == sorted(second.items)


def test_importing_an_item_twice_gives_the_same_record():
    text, _losses = export_item(every_category_weapon(), SYNTHETIC_NAMING)
    kwargs = dict(record_id="r", created_at=CREATED_AT,
                  catalog_hash=CATALOG_HASH)
    assert (import_item(text, SYNTHETIC_NAMING, **kwargs).item_hash
            == import_item(text, SYNTHETIC_NAMING, **kwargs).item_hash)


def test_the_round_trip_itself_detects_a_mutating_conversion(monkeypatch):
    """The guard has to fail when something does mutate; otherwise it is decoration."""
    from pob2opt.evaluation import roundtrip as module

    real = module.export_build

    def mutating(build, items, naming, **kwargs):
        items["injected-by-a-defective-exporter"] = every_category_weapon()
        return real(build, items, naming, **kwargs)

    monkeypatch.setattr(module, "export_build", mutating)
    with pytest.raises(SourceMutated):
        round_trip(*supported_build(), SYNTHETIC_NAMING)
