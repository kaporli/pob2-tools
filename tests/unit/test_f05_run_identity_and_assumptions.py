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
that cannot run without PoB, so the test pins the literals and the repair
removes them.

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


def test_point_budgets_are_not_derived_from_a_catalog():
    assert "catalog" not in SOURCE.lower()
    assert "patch_profile" not in SOURCE


# ----------------------------------------- 4. candidate lists are hard-capped

#: Literal truncations of ranked candidate lists in the phase pipeline.
LITERAL_SLICES = re.compile(r"\)\[:\d+\]|\][:\s]*\[:\d+\]|\[:\d+\]")


def literal_slice_count() -> int:
    return len(LITERAL_SLICES.findall(SOURCE))


def test_candidate_lists_are_truncated_by_literal_slices():
    assert literal_slice_count() >= 6
    assert re.search(r'"--top",\s*type=int,\s*default=8', SOURCE)


# ------------------------------------------------------- repaired behaviour

@pytest.mark.xfail(
    strict=True,
    reason="F05 repair is P08-T01: evaluation reuse must require a full identity "
           "match (request, catalog, patch profile, engine revision), not a filename.",
)
def test_repaired_cache_requires_a_matching_run_identity():
    params = set(inspect.signature(cli.load_phase).parameters)
    assert params & {"identity", "manifest", "run_id", "cache_key"}


@pytest.mark.xfail(
    strict=True,
    reason="F05 repair is P08-T01: the league must be resolved during prepare and "
           "frozen in the run manifest, not defaulted in the argument parser.",
)
def test_repaired_league_is_not_hardcoded():
    assert "Forbidden Rites" not in SOURCE


@pytest.mark.xfail(
    strict=True,
    reason="F05/P02-T02 repair: quest-passive and ascendancy budgets must come "
           "from the pinned catalog, not from level thresholds in the CLI.",
)
def test_repaired_point_budgets_are_catalog_derived():
    assert not any(f in SOURCE for f in QUEST_POINT_FORMULAS)
    assert not any(f in SOURCE for f in ASCENDANCY_FORMULAS)


@pytest.mark.xfail(
    strict=True,
    reason="F05 repair is P08-T01/P08-T03: result-set size belongs to the run "
           "request, not to literal slices inside the phases.",
)
def test_repaired_result_sets_are_not_literal_slices():
    assert literal_slice_count() == 0
