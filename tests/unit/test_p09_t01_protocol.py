"""Every protocol field is sourced or explicitly unresolved (P09-T01).

The task's single rule is that a field nobody can source becomes an unresolved
input with a named DataGap, never a plausible-looking number. These tests are
how that rule is enforced mechanically rather than by reading:

* every ScenarioSpec field appears in the field table,
* a field marked ``unresolved_input`` names at least one gap that exists,
* a field marked anything else names none,
* every gap states a collectable request, not "need more data",
* the field table claims no direct measurement, because none was taken.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

import p09_t01_suite as suite
from pob2opt.domain.records import RecordBase, ScenarioSpec

RECORD_BASE_FIELDS = {f.name for f in dataclasses.fields(RecordBase)}
SCENARIO_FIELDS = {
    f.name for f in dataclasses.fields(ScenarioSpec)
} - RECORD_BASE_FIELDS


@pytest.fixture(scope="module")
def fields(repo_root: Path) -> dict:
    path = repo_root / "docs" / "evidence" / "P09" / "protocol-fields.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def bundle(fixtures_dir: Path) -> dict:
    path = fixtures_dir / "combat" / "p09_synthetic_suite.v1.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def gap_ids(bundle: dict) -> set:
    return {g["gap_id"] for g in bundle["records"]["data_gap"]}


# ------------------------------------------------------------ completeness

def test_the_field_table_covers_every_scenario_spec_field(fields: dict):
    covered = {row["field"].split(".")[0] for row in fields["fields"]}
    assert covered == SCENARIO_FIELDS


def test_the_committed_field_table_is_what_the_generator_produces(fields: dict, gap_ids: set):
    assert fields["fields"] == suite.build_field_plan(gap_ids)


# ------------------------------------------------------- sourced or unresolved

def test_every_row_is_sourced_or_unresolved_and_never_both(fields: dict):
    for row in fields["fields"]:
        status = row["representative_status"]
        assert status in ("sourced", "unresolved_input"), row["field"]
        if status == "unresolved_input":
            assert row["gap_ids"], row["field"]
        else:
            assert row["gap_ids"] == [], row["field"]


def test_every_named_gap_exists_in_the_bundle(fields: dict, gap_ids: set):
    for row in fields["fields"]:
        for gap in row["gap_ids"]:
            assert gap in gap_ids, (row["field"], gap)


def test_every_row_states_where_its_value_came_from(fields: dict):
    allowed = {"specification", "product_default", "test_constant", "unresolved"}
    for row in fields["fields"]:
        assert row["synthetic_basis"] in allowed, row["field"]
        assert row["source_or_reason"].strip(), row["field"]


def test_no_field_claims_a_direct_measurement(fields: dict):
    """Nothing in this suite was measured. A row claiming otherwise would be
    the failure this task exists to prevent."""
    bases = {row["synthetic_basis"] for row in fields["fields"]}
    assert "measured" not in bases
    assert "gameplay" not in bases


def test_the_unresolved_half_is_the_larger_half(fields: dict):
    """Not a quality bar. It records that most of this protocol is unknown, so
    a later edit that silently resolves rows has to change this number."""
    unresolved = [r for r in fields["fields"]
                  if r["representative_status"] == "unresolved_input"]
    assert len(unresolved) == 17
    assert len(fields["fields"]) == 26


# ---------------------------------------------------------------- the gaps

def test_every_gap_is_open_and_names_a_collectable_request(bundle: dict):
    vacuous = {"need more data", "more data", "unknown", "tbd", "todo"}
    for gap in bundle["records"]["data_gap"]:
        assert gap["status"] == "open", gap["gap_id"]
        assert gap["needed_evidence"].strip().lower().rstrip(".") not in vacuous
        assert gap["collection_method"].strip(), gap["gap_id"]
        assert gap["field_paths"], gap["gap_id"]
        assert gap["subject_ids"], gap["gap_id"]


def test_the_blocking_gaps_are_the_ones_that_stop_a_measurement(bundle: dict):
    severity = {g["gap_id"]: g["severity"] for g in bundle["records"]["data_gap"]}
    for gap_id in ("gap-p09-t01-enemy-health", "gap-p09-t01-enemy-defenses",
                   "gap-p09-t01-incoming-damage", "gap-p09-t01-boss-windows",
                   "gap-p09-t01-reference-build", "gap-p09-t01-build-families"):
        assert severity[gap_id] == "blocking", gap_id


def test_the_build_family_question_is_recorded_as_access_blocked(bundle: dict):
    gap = next(g for g in bundle["records"]["data_gap"]
               if g["gap_id"] == "gap-p09-t01-build-families")
    assert gap["kind"] == "access_blocked"
    assert "corpus" in gap["needed_evidence"]
    assert gap["severity"] == "blocking"


def test_no_build_family_is_named_anywhere_in_the_suite(bundle: dict):
    """P09-T01 was asked for three Huntress families and has none. The suite
    must not contain a family-shaped identifier that a later reader could take
    for a selection."""
    text = json.dumps(bundle, ensure_ascii=False)
    assert '"family_id"' not in text
    assert "build_family_id" not in text


# ------------------------------------------------------------- the protocol

def test_the_protocol_document_exists_and_refuses_the_claims_it_cannot_make(
        repo_root: Path):
    path = repo_root / "benchmarks" / "p09-synthetic-v1" / "protocol.md"
    text = path.read_text(encoding="utf-8")
    assert "synthetic" in text.lower()
    assert "clear speed" in text
    assert "kill time" in text
    # The protocol must not present itself as accepted.
    assert "not accepted" in text


def test_the_decision_record_keeps_d04_blocked_for_practical_claims(
        repo_root: Path):
    """What has to hold is the restriction, not the word "Unresolved".

    This used to require the record to say it was unresolved whatever a
    reviewer decided, which forbade the lifecycle it exists inside. A reviewer
    may resolve the technical half; what may not change without new evidence
    is that the representative suite and the build families stay unselected
    and that nothing here is a practical claim.
    """
    text = (repo_root / "docs" / "decisions" / "D04-encounter-suite.md").read_text(
        encoding="utf-8")
    for heading in ("## Question", "## Sources consulted", "## What was observed",
                    "## Proposed choice", "## Contracts affected", "## Reviewer",
                    "## Date"):
        assert heading in text, heading
    assert "blocked for practical claims" in text
    assert "Select no encounters" in text
    assert "Select no Huntress build families" in text
    assert "Fit no constant" in text
    assert "validation: synthetic_only" in text
    # Items 2 and 3 are not a reviewer's to resolve on this evidence.
    assert "**Unresolved.** Items 2 and 3" in text
