"""Independent follow-up probes; software cases, not gameplay evidence."""
import json
import sys
import tempfile
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
for sub in ('pob2-mcp', 'pob2-optimizer', 'tests', 'tests/unit', 'scripts'):
    sys.path.insert(0, str(repo / sub))

out = {}
if (repo / 'pob2-optimizer/pob2opt/coverage').exists():
    import test_p06_coverage as c
    xml = '''<PathOfBuilding2><Build className="Monk" level="90" mainSocketGroup="1"/>
    <Skills><Skill enabled="true"><Gem skillId="Strike" enabled="true"/>
    <Gem skillId="SupportGate" enabled="true"/></Skill>
    <Skill enabled="true"><Gem skillId="Builder" enabled="true"/></Skill></Skills>
    <Tree><Spec nodes=""/></Tree><Config activeConfigSet="1"><ConfigSet id="1">
    <CustomModifierBlock enabled="true">1000% more Damage</CustomModifierBlock>
    </ConfigSet></Config></PathOfBuilding2>'''
    facts = c.build_facts_from_pob_xml(xml, engine=c.EngineState(c.PIN,False))
    report, decision = c.run(b=facts,ms=c.capture(facts))
    out['custom_modifier_coverage'] = {'eligible':decision.eligible,'blocking':c.classes(report),
                                      'config_explicit':dict(facts.config_explicit)}
if (repo / 'pob2-optimizer/pob2opt/combat').exists():
    import test_p07_t01_flicker_cycle as f
    with tempfile.TemporaryDirectory() as temp:
        bench = Path(temp) / 'scenarios.json'
        bench.write_text(json.dumps({'data_gaps': [], 'scenarios': [
            {'scenario_id':'flicker_sustained_v1','category':'dps_benchmark','fields':{}}]}))
        base = f.SYNTH_XML % ''
        xml = base.replace('</PathOfBuilding2>', '<Config activeConfigSet="1"><ConfigSet id="1">'
            '<CustomModifierBlock enabled="true" title="Unverified">1000% more Damage</CustomModifierBlock>'
            '</ConfigSet></Config></PathOfBuilding2>')
        ident = f.identity(xml)
        result = f.evaluate(bench, f.settled(), xml=xml, source=f.values(engine=ident))
        out['custom_modifier'] = {'status':result.status,'score':result.objective['score'],
            'blocking':result.decision['blocking'],
            'captured_config':ident['parse_capture']['config']}

if (repo / 'pob2-optimizer/pob2opt/catalog/slotrules.py').exists():
    import copy
    import test_p02_t03_1_slot_rules as s
    from pob2opt.catalog.slotrules import decide
    probe = json.loads(s.PROBE.read_text())['slotAcceptance']
    for row in probe['slots']:
        if row['slot'] == 'Weapon 1':
            row['categories']['Bow']['accepted'] = 0
    export = s._export(probe)
    rule = next(r for r in export.profile.character_rules.slots if r.slot_id == s.S+'Weapon 1')
    rows = json.loads(s.SLICE.read_text())['tables']['item_bases']
    bow = next(r for r in rows if r['type'] == 'Bow')
    report = s._validate(export, {'bow':('Weapon 1',bow['name'])},rarity={'bow':'unique'})
    out['inverse_rarity'] = {'raw_decision':decide(rule,bow,'unique'),
        'legality':report.decision(s.CHECK_SLOTS).value,
        'undecided_rarities':rule.undecided_rarities,'violations':report.violation_codes}

Path(sys.argv[2]).write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out,indent=2))
