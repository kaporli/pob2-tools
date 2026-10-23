"""Independent review probes. Run: python review_probes.py CHECKOUT OUTPUT.json.

Uses the delivery's settled synthetic fixtures to isolate contract failures;
these are software probes, not gameplay evidence. No engine or network calls.
"""
import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
for sub in ('pob2-mcp', 'pob2-optimizer', 'tests', 'tests/unit', 'scripts'):
    sys.path.insert(0, str(repo / sub))

import test_p06_coverage as c
from pob2opt.coverage.inputs import build_facts_from_pob_xml

out = {}
xml = '''<PathOfBuilding2><Build level="90"/><Skills activeSkillSet="2">
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
facts = build_facts_from_pob_xml(xml)
out['active_sets'] = dict(skills=[g.skill_id for group in facts.groups for g in group.gems],
                          passives=facts.passive_ids, items=[i.item_id for i in facts.items],
                          config=dict(facts.config_explicit))

report, decision = c.run(b=replace(c.build(), config_explicit={'conditionOnslaught': True}), ms=c.mods(config=()))
out['stale_config_evidence'] = dict(eligible=decision.eligible, blocking=c.classes(report))
report, decision = c.run(b=c.build(passives=('99999999',)), ms=c.mods(nodes={}))
out['missing_passive_evidence'] = dict(eligible=decision.eligible, blocking=c.classes(report))
report, decision = c.run(b=c.build(items=(c.ItemFacts('Ring 1', 'changed-item', 'New unsupported item'),)),
                        ms=replace(c.mods(items={'Ring 1': ()}), pob_commit='wrong-commit'))
out['stale_item_wrong_engine_evidence'] = dict(eligible=decision.eligible, blocking=c.classes(report))

target = c.entry('target/bench', owner=c.SCN, domain='target', subjects=('scenario:bench',))
reg = c.settled_registry(**{'target/bench': target})
report, decision = c.run(reg, ms=c.mods(config=({'var':'enemyCriticalWeaknessStacks', 'input':20, 'shown':True},)))
out['unearned_enemy_critical_weakness'] = dict(eligible=decision.eligible, blocking=c.classes(report), rules=report.rule_ids)

if (repo / 'pob2-optimizer/pob2opt/combat').exists():
    import test_p07_t01_flicker_cycle as f
    from pob2opt.combat import AttributionTable
    from pob2opt.combat.attribution import FLICKER_HIT, WHIRLING_HIT
    with tempfile.TemporaryDirectory() as temp:
        bench = Path(temp) / 'scenarios.json'
        bench.write_text(json.dumps({'data_gaps': [], 'scenarios': [
            {'scenario_id':'flicker_sustained_v1', 'category':'dps_benchmark', 'fields':{}}]}))
        def result(r):
            return dict(status=r.status, id=r.evaluation_id, score=r.objective['score'], method=r.method)
        base = f.evaluate(bench, f.settled())
        shorter = f.evaluate(bench, f.settled(), window_s=12.0)
        burst = f.evaluate(bench, f.settled(), burst_s=1.0)
        out['window_identity'] = {'normal': result(base), 'short': result(shorter), 'burst': result(burst)}
        table = AttributionTable.from_rows('unaccepted-different-table', [(FLICKER_HIT, 'flicker_direct'),
                                                                       (WHIRLING_HIT, 'flicker_secondary')])
        wrong_owner = f.evaluate(bench, f.settled(), source=f.values(whirling_damage_per_use=1e12), attribution=table)
        out['unaccepted_attribution'] = result(wrong_owner)
        foreign_engine = f.evaluate(bench, f.settled(), source=f.values(engine={'head':'wrong-commit', 'dirty_hash':'dirty'}))
        out['foreign_engine_values'] = result(foreign_engine)
        other_method = f.evaluate(bench, f.settled(), method='pob-cycle-v1')
        out['unsupported_method'] = result(other_method)

Path(sys.argv[2]).write_text(json.dumps(out, indent=2), encoding='utf-8')
print(json.dumps(out, indent=2))
