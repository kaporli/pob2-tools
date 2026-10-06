"""Research finding F11 and its repair (P00-T04 characterization, P02-T01 fix).

``pob2opt.engine_worker.Worker`` used to load a character XML and then
immediately call ``OPT_setup``, which resets the passive tree, disables every
socket group and clears every item slot. Nothing of the imported character
survived, so that code path could not evaluate a community build faithfully.

P02-T01 split the two steps. Construction now loads the document and stops;
``create_blank_build`` is the separate, explicitly destructive operation that
the legacy phase pipeline calls through ``new_blank_worker``. The assertions
that pinned the old combined sequence were migrated accordingly: they now pin
the split, because the previous behaviour is the defect.

These tests use a recording double in place of ``Pob2Engine``; no PoB runtime is
involved. ``tests/engine/test_f11_import_is_wiped.py`` measures the same thing
against the real engine.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pob2opt import engine_worker

BUILD_XML = "<PathOfBuilding2><!-- fixture character --></PathOfBuilding2>"


class RecordingEngine:
    """Stands in for ``pob2mcp.engine.Pob2Engine``; records every call."""

    def __init__(self, pob_root: str):
        self.pob_root = pob_root
        self.calls: list[tuple[str, object]] = []

    def call(self, fn: str, args=None):
        self.calls.append(("call:" + fn, args))
        return {}

    def eval_lua(self, code: str):
        self.calls.append(("eval", code))
        return True

    @property
    def transcript(self) -> list[str]:
        out = []
        for kind, payload in self.calls:
            if kind == "eval":
                head = str(payload).strip().split("(")[0].splitlines()[-1].strip()
                out.append("eval:" + (head or "<lua chunk>"))
            else:
                out.append(kind)
        return out


@pytest.fixture()
def recording_worker(monkeypatch):
    engines: list[RecordingEngine] = []

    def factory(pob_root):
        engine = RecordingEngine(pob_root)
        engines.append(engine)
        return engine

    import pob2mcp.engine as real_engine_module

    monkeypatch.setattr(real_engine_module, "Pob2Engine", factory)
    worker = engine_worker.Worker(
        pob_root="FIXTURE-POB-ROOT", mcp_path="", build_xml=BUILD_XML,
        char_level=60, resist_penalty=0,
    )
    return worker, engines[0]


# ------------------------------------------------------- current behaviour

def test_worker_init_loads_the_build_and_stops_there(recording_worker):
    """Migrated by P02-T01: construction used to call OPT_setup as well."""
    _, engine = recording_worker
    transcript = engine.transcript

    assert "call:load_build_xml" in transcript
    assert not [s for s in transcript if s.startswith("eval:return OPT_setup")]


def test_the_legacy_entry_point_still_clears_the_build_before_searching(monkeypatch):
    """The destructive step did not disappear; it became explicit and named."""
    engines: list[RecordingEngine] = []

    def factory(pob_root):
        engine = RecordingEngine(pob_root)
        engines.append(engine)
        return engine

    import pob2mcp.engine as real_engine_module

    monkeypatch.setattr(real_engine_module, "Pob2Engine", factory)
    engine_worker.new_blank_worker("FIXTURE-POB-ROOT", "", BUILD_XML, 60, 0)
    transcript = engines[0].transcript

    setup_calls = [i for i, step in enumerate(transcript)
                   if step.startswith("eval:return OPT_setup")]
    assert setup_calls, "the legacy pipeline still needs a blank candidate"
    assert transcript.index("call:load_build_xml") < setup_calls[0]


def test_the_imported_xml_is_passed_through_unchanged(recording_worker):
    _, engine = recording_worker
    load = next(args for kind, args in engine.calls if kind == "call:load_build_xml")
    assert load["xml"] == BUILD_XML


def test_reset_repeats_the_same_destructive_sequence(recording_worker):
    worker, engine = recording_worker
    before = len([s for s in engine.transcript if s.startswith("eval:return OPT_setup")])
    worker.reset()
    after = len([s for s in engine.transcript if s.startswith("eval:return OPT_setup")])
    assert after == before + 1


def test_opt_setup_source_clears_tree_groups_and_items(repo_root: Path):
    """The mechanism behind the wipe, read from the helper that performs it."""
    source = (repo_root / "pob2-optimizer" / "pob2opt" / "lua" / "opt_helpers.lua").read_text(
        encoding="utf-8")
    body = re.search(r"function OPT_setup\(.*?\n(.*?)\nend\n", source, re.S)
    assert body, "OPT_setup not found in opt_helpers.lua"
    text = body.group(1)

    assert "build.spec:ResetNodes()" in text          # passive tree discarded
    assert "g.enabled = false" in text                # every socket group disabled
    assert "slot:SetSelItemId(0)" in text             # every equipped item removed


# ------------------------------------------------------- repaired behaviour

def test_exact_loading_does_not_reset_the_character(recording_worker):
    worker, engine = recording_worker
    before = len(engine.calls)
    worker.load_exact_build()

    new_steps = engine.transcript[before:]
    assert "call:load_build_xml" in new_steps
    assert not [s for s in new_steps if s.startswith("eval:return OPT_setup")]


def test_blank_and_exact_loading_are_separate_named_operations():
    assert hasattr(engine_worker.Worker, "load_exact_build")
    assert hasattr(engine_worker.Worker, "create_blank_build")


def test_the_production_adapter_offers_the_same_split():
    from pob2opt.evaluation import EngineAdapter

    assert hasattr(EngineAdapter, "load_exact_build")
    assert hasattr(EngineAdapter, "create_blank_build")
