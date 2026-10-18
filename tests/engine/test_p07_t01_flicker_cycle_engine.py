"""P07-T01 against the real PoB engine.

Live capture of the cycle values through ``EngineAdapter`` (including the new
read-only ``cycle_inputs`` operation) reproduces the frozen P09-T01.2 bundle,
and two captures in separate worker processes give identical evaluations.
Only a clean checkout of the pin may produce them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pob2opt.combat import capture, evaluate_flicker, from_replay, load_p09_resolutions
from pob2opt.evaluation import EngineAdapter, pob_worker_spec, resolve_checkout

pytestmark = pytest.mark.engine

PIN = "ce566eac45ea8a86477f513c7ee65a1ebe60014e"


def _adapter(pob_root: Path) -> EngineAdapter:
    return EngineAdapter(pob_worker_spec(pob_root), screen_timeout_s=300.0,
                         detailed_timeout_s=300.0, start_timeout_s=600.0,
                         max_requests_per_worker=4)


@pytest.fixture(scope="module")
def captures(pob_root: Path, repo_root: Path):
    checkout = resolve_checkout(pob_root)
    if checkout.commit != PIN or checkout.dirty_hash is not None:
        pytest.skip("cycle values belong to a clean checkout of %s" % PIN)
    xml = (repo_root / "docs/evidence/P09-T01.1/seed/export-flicker-main.xml").read_text(encoding="utf-8")
    out = []
    for label in ("a", "b"):
        adapter = _adapter(pob_root)
        try:
            values = capture(adapter, xml, build_hash="p07-t01-test/" + label)
        finally:
            adapter.close()
        out.append((values, list(adapter.worker_pids)))
    return xml, out


def _plain(values) -> dict:
    data = values.to_json()
    data.pop("engine")
    data.pop("trace")
    return data


def test_live_values_reproduce_the_frozen_bundle(captures, repo_root: Path):
    _, runs = captures
    replay = json.loads((repo_root / "docs/evidence/P09-T01.2/replay.json").read_text(encoding="utf-8"))
    frozen = _plain(from_replay(replay))
    live = _plain(runs[0][0])
    assert live.keys() == frozen.keys()
    for key, value in frozen.items():
        if value is None:
            continue  # the bundle has no benchmark-document value for it
        if isinstance(value, float):
            assert live[key] == pytest.approx(value, rel=1e-9), key
        else:
            assert live[key] == value, key


def test_fresh_workers_agree(captures):
    xml, ((a, pids_a), (b, pids_b)) = captures
    assert not set(pids_a) & set(pids_b)
    assert _plain(a) == _plain(b)
    p09 = load_p09_resolutions()
    ra, rb = evaluate_flicker(xml, a, p09_resolutions=p09), evaluate_flicker(xml, b, p09_resolutions=p09)
    for key in ("status", "objective", "decision", "diagnostic", "timeline", "repeatable"):
        assert ra.to_json()[key] == rb.to_json()[key], key
