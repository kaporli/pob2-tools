"""Read-only native confirmation that an uncaptured custom block changes DPS."""
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from pob2opt.coverage.capture import bind_capture
from pob2opt.coverage.inputs import select_loadout
from pob2opt.evaluation import BuildDocument, EngineAdapter, EngineState, pob_worker_spec

pytestmark = pytest.mark.engine


def test_custom_modifier_affects_damage_but_is_absent_from_bound_capture(pob_root, repo_root):
    xml = (repo_root/'docs/evidence/P09-T01.1/seed/export-flicker-main.xml').read_text(encoding='utf-8')
    root = ET.fromstring(xml)
    chosen, _, problems = select_loadout(root)
    assert not problems
    node = ET.SubElement(chosen['Config'],'CustomModifierBlock',title='Review probe',enabled='true')
    node.text = '1000% more Damage'
    changed = ET.tostring(root,encoding='unicode')
    adapter = EngineAdapter(pob_worker_spec(pob_root),max_requests_per_worker=4,
                            start_timeout_s=120,screen_timeout_s=120,detailed_timeout_s=120)
    try:
        state=EngineState(config={'usePowerCharges':True,'overridePowerCharges':5},
                          main_skill=(6,1),stat_keys=('AverageDamage',))
        plain=adapter.probe(BuildDocument(build_hash='review/plain',xml=xml),state)
        modified=adapter.probe(BuildDocument(build_hash='review/modified',xml=changed),state)
        raw=adapter.parse_support(BuildDocument(build_hash='review/modified-parse',xml=changed))
        identity=adapter.identity()
        bound=bind_capture(changed,raw,pob_commit=identity.pob_commit,pob_dirty=False)
        result={'baseline':plain,'modified':modified,
                'ratio':modified['AverageDamage']/plain['AverageDamage'],
                'custom_config_rows':[r for r in bound['config'] if 'custom' in r['var'].lower()],
                'binding_config_keys':sorted(bound['binding']['config']),
                'engine':{'commit':identity.pob_commit,'dirty_hash':identity.pob_dirty_hash}}
        Path(os.environ['REVIEW_NATIVE_OUTPUT']).write_text(json.dumps(result,indent=2),encoding='utf-8')
        # This checks a material native effect, not a linear scaling law:
        # downstream conditions can also change when damage changes.
        assert result['ratio'] > 10
        assert result['custom_config_rows'] == []
    finally:
        adapter.close()
