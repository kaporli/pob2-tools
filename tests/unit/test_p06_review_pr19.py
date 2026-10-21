"""PR #19 review probes (docs/reviews/PR-18-22.md R1 to R3) as regressions.

Each test is the reviewer's probe from ``docs/evidence/PR-18-22/review_probes.py``
with its expected repaired outcome. They use only the helpers that existed at
the reviewed head ``3cc334d``, so they run there and fail, and pass after the
repair. No engine.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_p06_coverage as c  # noqa: E402  (the reviewer's helper module)
from pob2opt.coverage.inputs import build_facts_from_pob_xml  # noqa: E402

TWO_LOADOUTS = '''<PathOfBuilding2><Build level="90"/><Skills activeSkillSet="2">
<SkillSet id="1"><Skill enabled="true"><Gem enabled="true" skillId="Strike"/></Skill></SkillSet>
<SkillSet id="2"><Skill enabled="true"><Gem enabled="true" skillId="UnknownActiveSkill"/></Skill></SkillSet>
</Skills><Tree activeSpec="2"><Spec nodes="1"/><Spec nodes="2"/></Tree>
<Items activeItemSet="2"><Item id="1">Rarity: RARE
First
Ring</Item><Item id="2">Rarity: RARE
Second
Ring</Item><ItemSet id="1"><Slot name="Ring 1" itemId="1"/></ItemSet>
<ItemSet id="2"><Slot name="Ring 1" itemId="2"/></ItemSet></Items>
<Config activeConfigSet="2"><ConfigSet id="1"/><ConfigSet id="2"><Input name="conditionOnslaught" boolean="true"/></ConfigSet></Config>
</PathOfBuilding2>'''


def test_r1_active_sets_are_read_not_the_first_ones():
    facts = build_facts_from_pob_xml(TWO_LOADOUTS)
    assert [g.skill_id for group in facts.groups for g in group.gems] == ["UnknownActiveSkill"]
    assert list(facts.passive_ids) == ["2"]
    assert [i.item_id for i in facts.items] == ["2"]
    assert dict(facts.config_explicit) == {"conditionOnslaught": True}


def test_r2_stale_config_evidence_blocks():
    report, decision = c.run(b=replace(c.build(), config_explicit={"conditionOnslaught": True}),
                             ms=c.mods(config=()))
    assert not decision.eligible
    assert c.classes(report)


def test_r2_missing_passive_evidence_blocks():
    report, decision = c.run(b=c.build(passives=("99999999",)), ms=c.mods(nodes={}))
    assert not decision.eligible
    assert c.classes(report)


def test_r2_changed_item_with_wrong_engine_evidence_blocks():
    report, decision = c.run(
        b=c.build(items=(c.ItemFacts("Ring 1", "changed-item", "New unsupported item"),)),
        ms=replace(c.mods(items={"Ring 1": ()}), pob_commit="wrong-commit"))
    assert not decision.eligible
    assert c.classes(report)


def test_r3_unearned_enemy_critical_weakness_blocks():
    target = c.entry("target/bench", owner=c.SCN, domain="target", subjects=("scenario:bench",))
    reg = c.settled_registry(**{"target/bench": target})
    report, decision = c.run(reg, ms=c.mods(config=(
        {"var": "enemyCriticalWeaknessStacks", "input": 20, "shown": True},)))
    assert not decision.eligible
    assert c.classes(report)


# ---------------------------------------- PR #19 re-review F1 (128064c) ===

CUSTOM_BLOCK = '''<PathOfBuilding2><Build level="90" mainSocketGroup="1"/>
    <Skills><Skill enabled="true"><Gem skillId="Strike" enabled="true"/>
    <Gem skillId="SupportGate" enabled="true"/></Skill>
    <Skill enabled="true"><Gem skillId="Builder" enabled="true"/></Skill></Skills>
    <Tree><Spec nodes=""/></Tree><Config activeConfigSet="1"><ConfigSet id="1">
    <CustomModifierBlock enabled="true">1000% more Damage</CustomModifierBlock>
    </ConfigSet></Config></PathOfBuilding2>'''


def test_f1_enabled_custom_modifier_block_blocks_with_everything_else_settled():
    facts = build_facts_from_pob_xml(CUSTOM_BLOCK, engine=c.EngineState(c.PIN, False))
    report, decision = c.run(b=facts, ms=c.capture(facts))
    assert not decision.eligible
    assert c.classes(report)
