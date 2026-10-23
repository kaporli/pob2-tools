"""P02-T02.1 against the real PoB engine.

What only the engine can establish:

* the export with the verbatim capture runs every fixture, including the
  three Flicker Strike behaviour fixtures, and none is unchecked;
* the verdict is still ``partial``, now without the summary reason, and
  without the checkout reason when the checkout is clean;
* the catalog's static support list for Flicker Strike equals PoB's own
  answer for the live main skill of the recorded Flicker Strike document.

One adapter serves the module.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pob2opt.catalog import (EngineCatalogReader, ExportRequest,
                             PobCatalogProvider, compatibility_fixtures)
from pob2opt.catalog.compatibility import MATCH
from pob2opt.catalog.release import load_release_captures
from pob2opt.catalog.sources import read_citations
from pob2opt.catalog.supports import skill_coverage
from pob2opt.domain.enums import Compatibility
from pob2opt.domain.objectives import FLICKER_SUSTAINED_DPS_V1
from pob2opt.evaluation import (BuildDocument, EngineAdapter, EngineState,
                                pob_worker_spec, resolve_checkout)

pytestmark = pytest.mark.engine

REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_DIR = REPO_ROOT / "docs" / "evidence" / "P02" / "release"
TIMEOUT_S = 300.0

#: PoB's own support check over every support effect, against the live main
#: skill. Same chunk as scripts/p02_t02_1_flicker_evidence.py.
LIVE_SUPPORTS_LUA = """
local skill = build.calcsTab.mainEnv.player.mainSkill
local accepted = {}
for id, effect in pairs(data.skills) do
  if effect.support then
    local ok, yes = pcall(calcLib.canGrantedEffectSupportActiveSkill, effect, skill)
    if ok and yes then accepted[#accepted + 1] = tostring(id) end
  end
end
table.sort(accepted)
return { skill = skill.activeEffect.grantedEffect.id, accepted = accepted }
"""


@pytest.fixture(scope="module")
def adapter(pob_root: Path):
    live = EngineAdapter(pob_worker_spec(pob_root), screen_timeout_s=TIMEOUT_S,
                         detailed_timeout_s=TIMEOUT_S, start_timeout_s=600.0)
    try:
        yield live
    finally:
        live.close()


@pytest.fixture(scope="module")
def checkout(pob_root: Path):
    return resolve_checkout(pob_root)


@pytest.fixture(scope="module")
def live_export(adapter, pob_root: Path, checkout):
    def behaviour(fixture):
        document = BuildDocument(build_hash="compat/%s" % fixture["fixture_id"],
                                 xml=fixture["document"])
        state = EngineState(stat_keys=tuple(sorted(fixture.get("expected") or {})))
        return adapter.probe(document, state, timeout_s=TIMEOUT_S)

    provider = PobCatalogProvider(
        EngineCatalogReader(adapter, timeout_s=TIMEOUT_S),
        citations=read_citations(pob_root),
        release_captures=load_release_captures(RELEASE_DIR),
        pob_commit=checkout.commit, pob_dirty_hash=checkout.dirty_hash,
        behaviour=behaviour)
    return provider.export(ExportRequest())


def _fixture(fixture_id: str) -> dict:
    return next(f for f in compatibility_fixtures()["fixtures"]
                if f["fixture_id"] == fixture_id)


def test_every_fixture_matches_including_flicker_behaviour(live_export):
    outcomes = live_export.report.outcomes
    assert [o.fixture_id for o in outcomes if o.outcome != MATCH] == []
    flicker = [o for o in outcomes if "flicker" in o.fixture_id]
    assert {o.kind for o in flicker} >= {"availability", "field", "members",
                                         "behaviour"}


def test_the_verdict_is_partial_for_the_stated_reasons_only(live_export, checkout):
    assert live_export.profile.compatibility is Compatibility.PARTIAL
    reasons = " ".join(live_export.report.reasons)
    assert "summary" not in reasons
    assert "predates" in reasons
    # P02-T03.1 reads slot categories from the engine, so the P02-T02 slot
    # gap is no longer among the reasons.
    assert "slot-accepted-base-categories" not in reasons
    if checkout.dirty_hash is None:
        assert "not a clean pinned tree" not in reasons
    else:
        assert "not a clean pinned tree" in reasons


def test_flicker_strike_has_no_coverage_issue_in_the_live_catalog(live_export):
    coverage = skill_coverage(live_export.catalog.entities,
                              FLICKER_SUSTAINED_DPS_V1.target_skill)
    assert coverage["issues"] == []
    assert coverage["compatible_support_gems"]


def test_the_static_support_list_equals_pobs_answer_in_a_build(live_export, engine):
    xml = _fixture("behaviour/flicker-strike-alone")["document"]
    engine.call("load_build_xml", {"xml": xml, "name": "p02-t02.1 flicker"})
    live = engine.eval_lua(LIVE_SUPPORTS_LUA)
    assert live["skill"] == "FlickerStrikePlayer"
    coverage = skill_coverage(live_export.catalog.entities,
                              FLICKER_SUSTAINED_DPS_V1.target_skill)
    assert sorted(live["accepted"]) == sorted(coverage["supported_by_effect_ids"])
