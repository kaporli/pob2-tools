"""Independent real-engine check of generated-group support preservation.

Uses committed synthetic PoB fixtures and the configured pinned local engine.
No provider, credentials, or gameplay. Writes source/export XML beside this file.
"""
import copy
import faulthandler
import json
import math
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
for path in (ROOT / 'pob2-mcp', ROOT / 'pob2-optimizer', ROOT / 'tests'):
    sys.path.insert(0, str(path))
import p04_fixtures as fx
from pob2mcp.engine import Pob2Engine
from pob2opt.evaluation import export_build
from pob2opt.domain.absent import ABSENT
from pob2opt.domain.identity import build_hash
from pob2opt.domain.migrate import upgrade_build_spec
from pob2opt.parsers import parse_document
from pob2opt.parsers.resolve import class_for_document_name, naming_from_catalog


def main():
    root = ET.fromstring(fx.document_bytes('b09'))
    skill_set = root.find('Skills/SkillSet')
    for group in list(skill_set):
        if group.tag == 'Skill' and not group.get('source'):
            skill_set.remove(group)
    root.find('Build').set('mainSocketGroup', '1')
    support = next(g for g in ET.fromstring(fx.document_bytes('b12')).iter('Gem')
                   if g.get('skillId') == 'SupportAddedColdDamagePlayer')
    skill_set.find('Skill').append(copy.deepcopy(support))
    engine = Pob2Engine(os.environ['POB2_ROOT'])
    try:
        engine.call('load_build_xml', {'xml': ET.tostring(root, encoding='unicode')})
        source_xml = engine.call('save_build_xml')['xml']
        source_summary = engine.call('load_build_xml', {'xml': source_xml})
        source_stats = engine.call('get_stats', {'all': True})
        data = source_xml.encode('utf-8')
        outcome = parse_document(fx.source(data), data, fx.context())
        build = outcome.builds[0]
        class_id = class_for_document_name(fx.entities(), ET.fromstring(source_xml).find('Build').get('className'))
        naming = naming_from_catalog(fx.entities(), class_id=class_id).naming
        exported = export_build(build, {i.item_hash: i for i in outcome.items}, naming)
        export_summary = engine.call('load_build_xml', {'xml': exported.xml})
        export_stats = engine.call('get_stats', {'all': True})
        differences = {}
        for key in sorted(set(source_stats) | set(export_stats)):
            a, b = source_stats.get(key), export_stats.get(key)
            if isinstance(a, (int, float)) and not isinstance(a, bool):
                if not isinstance(b, (int, float)) or not math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9):
                    differences[key] = [a, b]
        (OUT / 'generated-support-source.xml').write_text(source_xml, encoding='utf-8')
        (OUT / 'generated-support-export.xml').write_text(exported.xml, encoding='utf-8')
        observation = {'parse_status': outcome.result.status.value,
                          'build_status': build.parse_status.value,
                          'issues': [i.code for i in outcome.result.issues],
                          'recommended_export': exported.recommended_deliverable,
                          'source_main_skill': source_summary['mainSkill'],
                          'export_main_skill': export_summary['mainSkill'],
                          'source_gems': [(g.get('skillId'), g.get('enabled')) for g in ET.fromstring(source_xml).iter('Gem')],
                          'stat_differences': differences}
        data = fx.document_bytes('b03')
        outcome = parse_document(fx.source(data), data, fx.context())
        build = outcome.builds[0]
        groups = [replace(g, main_skill_index=0,
                          skills=[replace(s, support_ids=[], supports=ABSENT) for s in g.skills])
                  for g in build.skill_groups]
        legacy = replace(build, schema_version=1, main_skill_group=ABSENT, skill_groups=groups)
        legacy = replace(legacy, build_hash=build_hash(legacy))
        upgraded = upgrade_build_spec(legacy, record_id='review/v2', created_at=fx.CREATED_AT)
        class_id = class_for_document_name(fx.entities(), ET.fromstring(data).find('Build').get('className'))
        naming = naming_from_catalog(fx.entities(), class_id=class_id).naming
        evaluated = []
        for candidate in (legacy, upgraded):
            exported = export_build(candidate, {i.item_hash: i for i in outcome.items}, naming)
            summary = engine.call('load_build_xml', {'xml': exported.xml})
            stats = engine.call('get_stats', {'all': True})
            evaluated.append({'schema_version': candidate.schema_version,
                              'recommended_export': exported.recommended_deliverable,
                              'main_skill': summary['mainSkill'], 'TotalDPS': stats.get('TotalDPS')})
        result = {'generated_support': observation, 'v1_migration': evaluated}
        (OUT / 'engine-observations-py312.json').write_text(json.dumps(result, indent=2, sort_keys=True), encoding='utf-8')
        print(json.dumps(result, indent=2, sort_keys=True))
    finally:
        engine.close()


if __name__ == '__main__':
    log_path = ROOT / 'runs/pr10-review-native.log'
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open('w') as fault_log:
        faulthandler.enable(file=fault_log)
        try:
            main()
        finally:
            faulthandler.disable()
