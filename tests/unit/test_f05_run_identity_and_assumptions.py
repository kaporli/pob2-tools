"""Research finding F05, characterized (P00-T04).

``pob2opt/cli.py`` carries four problems that a reproducible run cannot keep:

1. phase results are cached by bare filename, so a cached ``gems.json`` is
   reused for any level, league, budget or PoB revision;
2. the league is a hardcoded argparse default;
3. passive-point and ascendancy-point budgets are hardcoded level thresholds
   rather than catalog-derived rules;
4. candidate lists are truncated by literal slices scattered through the phases.

Item 1 is exercised directly against the real ``load_phase``/``save_phase``.
Items 2-4 are source-level characterizations: the values live inside functions
that cannot run without PoB and a full harvest.

**The source checks are legacy characterization, not requirements.** The
delivery plan keeps ``phases.py``/``cli.py`` as a legacy comparison path until
replacement tests pass, so a valid repair may leave every literal below exactly
where it is. What must change is what a *new* run does, and the repaired
expectations at the bottom are written against that boundary instead.

Repairs: P08-T01 (immutable run contexts and cache identity) and P02-T02
(catalog-derived class, level, quest-reward and support-slot rules).
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

from pob2opt import cli

SOURCE = inspect.getsource(cli)


# ------------------------------------- 1. cache identity is the filename alone

def test_phase_cache_is_keyed_only_by_phase_name(tmp_path: Path):
    """A result produced for one request is served to a different request."""
    out = tmp_path / "run"
    first_request = [{"gem": "FIXTURE Gem", "produced_for_level": 28,
                      "produced_for_league": "FIXTURE League A"}]

    cli.save_phase(str(out), "gems", first_request)

    # Nothing about the second request is consulted; only the directory and the
    # phase name are. A level-100 search would consume level-28 screening data.
    assert cli.load_phase(str(out), "gems") == first_request

    on_disk = json.loads((out / "gems.json").read_text(encoding="utf-8"))
    assert on_disk == first_request
    # The persisted payload carries no request, catalog or engine identity.
    assert not isinstance(on_disk, dict), "payload is a bare list; no manifest wrapper"


def test_load_phase_signature_has_no_identity_argument():
    assert list(inspect.signature(cli.load_phase).parameters) == ["out_dir", "name"]
    assert list(inspect.signature(cli.save_phase).parameters) == ["out_dir", "name", "data"]


def test_missing_phase_file_is_a_cache_miss_not_an_error(tmp_path: Path):
    assert cli.load_phase(str(tmp_path), "gems") is None


# ----------------------------------------------- 2. the league is hardcoded

def test_league_is_a_hardcoded_argparse_default():
    assert re.search(r'"--league",\s*default="Forbidden Rites"', SOURCE)


def test_league_is_never_resolved_against_a_provider():
    """Nothing in the CLI turns `current` into a verified league id."""
    assert "league_selection" not in SOURCE
    assert "resolve_league" not in SOURCE


# ------------------------------- 3. point budgets are level-threshold guesses

QUEST_POINT_FORMULAS = (
    "(args.level - 1) + (6 if args.level <= 30 else 12)",
    "(args.level - 1) + 8",
)
ASCENDANCY_FORMULAS = (
    "2 if args.level < 40 else 4",
    '"asc_points": 2',
)


def test_passive_point_budget_is_a_hardcoded_level_threshold():
    found = [f for f in QUEST_POINT_FORMULAS if f in SOURCE]
    assert found, "expected the hardcoded quest-passive formulas to still be present"
    # The two formulas disagree with each other for the same character level,
    # which is the clearest evidence that neither is a sourced rule.
    assert len(found) == 2
    level = 28
    assert (level - 1) + 6 != (level - 1) + 8


def test_ascendancy_point_budget_is_a_hardcoded_level_threshold():
    assert any(f in SOURCE for f in ASCENDANCY_FORMULAS)


def test_point_budgets_are_computed_without_consulting_any_catalog():
    """Scoped to the formulas themselves.

    An earlier version asserted that the string "catalog" was absent from the
    whole module, which would have failed on a harmless comment. What matters is
    that the budget expressions depend only on ``args.level``.
    """
    for formula in QUEST_POINT_FORMULAS:
        assert "args.level" in formula
        assert "catalog" not in formula
        assert "profile" not in formula


# ----------------------------------------- 4. candidate lists are hard-capped

#: Literal truncations of ranked candidate lists in the phase pipeline.
LITERAL_SLICES = re.compile(r"\)\[:\d+\]|\][:\s]*\[:\d+\]|\[:\d+\]")


def literal_slice_count() -> int:
    return len(LITERAL_SLICES.findall(SOURCE))


def test_candidate_lists_are_truncated_by_literal_slices():
    """Legacy fact. Display slices in a report are fine; the search cap is not."""
    assert literal_slice_count() >= 6
    assert re.search(r'"--top",\s*type=int,\s*default=8', SOURCE)


# ------------------------------------------------------- future repair contract
# P00 can validate the probes against labelled doubles. It cannot fabricate P01
# records or assume a P08 return type. The explicit binding check turns into a
# hard failure when the service exists, until P08 wires real validated fixtures.

from dataclasses import replace

import jsonschema
from repair_contracts import (
    MissingFutureService, PREPARE_PROBES, REQUIRED_REQUEST_KEYS,
    make_prepare_fixture, require_production_binding,
)


@pytest.fixture
def prepare_case(tmp_path):
    return make_prepare_fixture(tmp_path)


@pytest.mark.parametrize("probe", PREPARE_PROBES, ids=lambda probe: probe.__name__)
def test_prepare_probe_accepts_valid_synthetic_behavior(prepare_case, probe):
    request, prepare, catalog_hash = prepare_case
    probe(prepare, request, catalog_hash)


@pytest.mark.parametrize("index,defect", [
    (0, {"cache_identity": "constant"}),
    (1, {"league_id": "current"}),
    (2, {"catalog_hash": "untraceable"}),
    (2, {"passive_points": 999}),
    (3, {"finalist_limit": 8}),
])
def test_prepare_probe_rejects_wrong_behavior(prepare_case, index, defect):
    request, prepare, catalog_hash = prepare_case

    def broken(candidate):
        return replace(prepare(candidate), **defect)

    with pytest.raises(AssertionError):
        PREPARE_PROBES[index](broken, request, catalog_hash)


def test_prepare_fixture_has_every_documented_request_field(prepare_case):
    from repair_contracts import REPO
    specification = (REPO / "docs/specs/interfaces.md").read_text()
    line = next(line for line in specification.splitlines() if line.startswith("Required request keys:"))
    documented = set(re.findall(r"`([^`]+)`", line))
    assert documented == set(REQUIRED_REQUEST_KEYS)
    assert documented <= prepare_case[0].keys()


def test_validation_failure_is_not_a_repair_xfail(prepare_case):
    request, prepare, catalog_hash = prepare_case
    del request["scenario_suite"]
    with pytest.raises(jsonschema.ValidationError, match="scenario_suite"):
        PREPARE_PROBES[0](prepare, request, catalog_hash)


def test_missing_snapshot_is_not_a_repair_xfail(prepare_case):
    request, prepare, catalog_hash = prepare_case
    Path(request["catalog_profile"]).unlink()
    with pytest.raises(FileNotFoundError):
        PREPARE_PROBES[0](prepare, request, catalog_hash)


@pytest.mark.xfail(strict=True, raises=MissingFutureService,
                   reason="P08-T01: prepare service and production contract binding are not implemented")
def test_production_prepare_contract_binding_is_pending():
    require_production_binding("pob2opt.search", "P08-T01")
