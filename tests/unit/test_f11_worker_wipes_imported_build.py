"""Research finding F11, characterized (P00-T04).

``pob2opt.engine_worker.Worker`` loads a character XML and then immediately
calls ``OPT_setup``, which resets the passive tree, disables every socket group
and clears every item slot. Nothing of the imported character survives, so the
same code path cannot be used to evaluate a community build faithfully.

These tests use a recording double in place of ``Pob2Engine``; no PoB runtime is
involved. ``tests/engine/test_f11_import_is_wiped.py`` proves the same thing
against the real engine. The repair is P02-T01 ("Define ``load_exact_build``
separately from ``create_blank_build``; exact loading must not call
``OPT_setup``").
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

def test_worker_init_loads_the_build_then_calls_opt_setup(recording_worker):
    _, engine = recording_worker
    transcript = engine.transcript

    assert "call:load_build_xml" in transcript
    setup_calls = [i for i, step in enumerate(transcript) if step.startswith("eval:return OPT_setup")]
    assert setup_calls, "expected OPT_setup to run during Worker.__init__"
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

@pytest.mark.xfail(
    strict=True,
    reason="F11 repair is P02-T01: loading an exact build must not call OPT_setup, "
           "which clears the tree, the socket groups and the equipment.",
)
def test_repaired_exact_load_does_not_reset_the_character(recording_worker):
    _, engine = recording_worker
    assert not [s for s in engine.transcript if s.startswith("eval:return OPT_setup")]


@pytest.mark.xfail(
    strict=True,
    reason="F11 repair is P02-T01: blank-candidate construction and faithful "
           "import must be separate, named operations on the adapter.",
)
def test_repaired_adapter_separates_blank_and_exact_loading():
    assert hasattr(engine_worker.Worker, "load_exact_build")
    assert hasattr(engine_worker.Worker, "create_blank_build")
