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


# ------------------------------------------------------- repaired behaviour
#
# P08-T01 promises an immutable run manifest: patch, league, catalog, corpus and
# item snapshots resolved once and frozen, with evaluation reuse keyed on that
# identity. P02-T02 promises catalog-derived point budgets. These expectations
# are written against those boundaries.
#
# They are deliberately NOT "the literal disappeared from cli.py". The legacy
# phase pipeline is allowed to keep its literals and its filename cache; what
# must not happen is a *new* run inheriting them. They currently fail because
# `pob2opt.search` does not exist yet.


def prepare_run(request):
    """The future prepare step, or a failure that keeps the xfail honest."""
    from pob2opt.search import prepare  # noqa: F401  (does not exist yet)

    return prepare(request)


BASE_REQUEST = {
    "schema_version": 1, "game": "poe2", "class": "Huntress", "level": 100,
    "patch_selection": "current", "league_selection": "current",
    "mode": "offline_items", "budget": None, "seed": 1,
}


@pytest.mark.xfail(
    strict=True,
    reason="F05 repair is P08-T01: evaluation reuse must be keyed on the full "
           "resolved run identity, so two different requests cannot share a "
           "cached result. Keeping load_phase for the legacy path is fine.",
)
def test_repaired_two_different_requests_get_different_cache_identities():
    low = prepare_run(dict(BASE_REQUEST, level=28))
    high = prepare_run(dict(BASE_REQUEST, level=100))

    assert low.cache_identity != high.cache_identity
    assert prepare_run(dict(BASE_REQUEST, level=28)).cache_identity == low.cache_identity


@pytest.mark.xfail(
    strict=True,
    reason="F05 repair is P08-T01: `current` must be resolved to an immutable "
           "league id at prepare time and frozen in the manifest.",
)
def test_repaired_league_is_resolved_and_frozen_in_the_manifest():
    manifest = prepare_run(dict(BASE_REQUEST)).manifest

    assert manifest["league"]["selection"] == "current"
    assert manifest["league"]["resolved_id"]
    assert manifest["league"]["resolved_id"] != "current"


@pytest.mark.xfail(
    strict=True,
    reason="F05/P02-T02 repair: quest-passive and ascendancy budgets must be "
           "derived from the pinned catalog and traceable to it.",
)
def test_repaired_point_budgets_come_from_the_catalog():
    manifest = prepare_run(dict(BASE_REQUEST)).manifest
    budgets = manifest["point_budgets"]

    assert budgets["source"] == "catalog"
    assert budgets["catalog_hash"]
    assert isinstance(budgets["passive_points"], int)
    assert isinstance(budgets["ascendancy_points"], int)


@pytest.mark.xfail(
    strict=True,
    reason="F05 repair is P08-T01/P08-T03: how many candidates a new search "
           "keeps belongs to the request, not to a literal slice.",
)
def test_repaired_candidate_limits_come_from_the_request():
    manifest = prepare_run(dict(BASE_REQUEST, finalist_limit=64)).manifest
    assert manifest["search"]["finalist_limit"] == 64
