"""P09-T01.2 against the real PoB engine.

The committed replay is reproducible: the seed and the benchmark document,
loaded unchanged through ``EngineAdapter`` at 0 and 5 forced Power Charges,
give the values in ``docs/evidence/P09-T01.2/replay.json``. Only a clean
checkout of the pin may produce them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import p09_t01_2_seed_replay as replay_script
from pob2opt.evaluation import (BuildDocument, EngineAdapter, EngineState,
                                pob_worker_spec, resolve_checkout)

pytestmark = pytest.mark.engine

TIMEOUT_S = 300.0
KEYS = ("AverageBurstHits", "AverageDamage", "AverageBurstDamage", "Speed", "ManaCost")


@pytest.fixture(scope="module")
def adapter(pob_root: Path):
    checkout = resolve_checkout(pob_root)
    if checkout.commit != replay_script.PIN or checkout.dirty_hash is not None:
        pytest.skip("replay values belong to a clean checkout of %s" % replay_script.PIN)
    live = EngineAdapter(pob_worker_spec(pob_root), screen_timeout_s=TIMEOUT_S,
                         detailed_timeout_s=TIMEOUT_S, start_timeout_s=600.0,
                         max_requests_per_worker=replay_script.MAX_REQUESTS_PER_WORKER)
    try:
        yield live
    finally:
        live.close()


@pytest.fixture(scope="module")
def committed(repo_root: Path) -> dict:
    return json.loads((repo_root / "docs" / "evidence" / "P09-T01.2" / "replay.json")
                      .read_text(encoding="utf-8"))


@pytest.mark.parametrize("document", ["seed", "benchmark"])
@pytest.mark.parametrize("charges", [0, 5])
def test_replay_values_reproduce(adapter, committed, repo_root: Path, document, charges):
    xml = replay_script.SEED_XML.read_text(encoding="utf-8")
    rows = committed["flicker_seed"]
    if document == "benchmark":
        xml = replay_script.disable_group(xml, replay_script.GROUP_POUNCE)
        rows = committed["benchmark_documents"]["flicker_benchmark"]
    config = {} if charges == 0 else {"usePowerCharges": True, "overridePowerCharges": charges}
    values = adapter.probe(
        BuildDocument(build_hash="p09-t01.2-test/%s/%d" % (document, charges), xml=xml),
        EngineState(config=config, main_skill=(replay_script.GROUP_FLICKER, 1), stat_keys=KEYS),
        timeout_s=TIMEOUT_S)
    expected = next(r for r in rows if r["forced_power_charges"] == charges)
    for key in KEYS:
        assert values[key] == pytest.approx(expected[key], rel=1e-9), key
