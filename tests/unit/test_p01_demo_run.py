"""The P01 end-to-end example still runs and still says the same thing.

``scripts/p01_demo_run.py`` produced ``docs/evidence/P01/demo-run.json``.
Evidence nobody re-runs rots, so this executes the script into a temporary
directory and checks the claims the worklog makes from it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def demo(tmp_path_factory, repo_root: Path) -> dict:
    sys.path.insert(0, str(repo_root / "scripts"))
    from p01_demo_run import build

    return build(tmp_path_factory.mktemp("p01-demo"))


def step(demo: dict, name: str) -> dict:
    return next(s for s in demo["steps"] if s["step"] == name)


def test_identical_bytes_are_ingested_once(demo: dict):
    ingest = step(demo, "ingest")
    assert ingest["first_write_reused_an_existing_blob"] is False
    assert ingest["second_write_reused_an_existing_blob"] is True
    assert ingest["source_records"] == 1


def test_the_bundle_is_readable_without_its_corpus(demo: dict):
    check = step(demo, "corpus_disconnected")["self_check"]
    assert check["readable"] is True
    assert check["missing_blobs"] == [] and check["missing_records"] == []
    assert check["records_declared"] == 6


def test_resume_keeps_the_completed_result_exactly_once(demo: dict):
    resume = step(demo, "resume")
    assert resume["already_completed"] == ["demo-task-1"]
    assert resume["recovered_from_running"] == ["demo-task-2"]
    assert resume["to_dispatch"] == ["demo-task-2", "demo-task-3"]
    assert resume["duplicate_message_created_a_second_result"] is False
    assert resume["evaluation_rows"] == 1


def test_the_stale_checkpoint_does_not_override_the_database(demo: dict):
    stale = step(demo, "checkpoint_is_stale")
    assert stale["checkpoint_completed_task_ids"] == []
    assert stale["database_completed_task_ids"] == ["demo-task-1"]


def test_a_legacy_phase_import_is_stored_and_marked_unusable(demo: dict):
    legacy = step(demo, "legacy_import")
    assert legacy["phase"] == "gems"
    assert legacy["cache_eligible"] is False


def test_the_cache_goes_cold_then_warm_but_never_down_a_fidelity(demo: dict):
    assert step(demo, "cold_cache")["reason"] == "no_entry"
    warm = step(demo, "warm_cache")
    assert warm["detailed"] == ["hit", "exact_match"]
    assert warm["screen"] == ["miss", "no_entry"]


def test_the_recorded_evidence_matches_a_fresh_run(demo: dict, repo_root: Path):
    recorded = json.loads(
        (repo_root / "docs/evidence/P01/demo-run.json").read_text(
            encoding="utf-8"))
    assert recorded["steps"] == demo["steps"], (
        "docs/evidence/P01/demo-run.json is stale; regenerate it with "
        "python scripts/p01_demo_run.py")
    assert set(recorded["inspection_queries"]) == \
        set(demo["inspection_queries"])
