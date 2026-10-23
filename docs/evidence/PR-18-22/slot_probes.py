"""Review of uncertainty propagation, using the delivery's probe mutation."""
import copy
import json
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
for sub in ('pob2-mcp', 'pob2-optimizer', 'tests', 'tests/unit', 'scripts'):
    sys.path.insert(0, str(repo / sub))
import test_p02_t03_1_slot_rules as s

probe = json.loads(s.PROBE.read_text())['slotAcceptance']
out = {}
changed = copy.deepcopy(probe)
for row in changed['slots']:
    if row['slot'] == 'Weapon 1':
        row['byRarity']['unique'].pop('Bow')
export = s._export(changed)
rows = json.loads(s.SLICE.read_text())['tables']['item_bases']
bow = next(r['name'] for r in rows if r['type'] == 'Bow')
report = s._validate(export, {'bow': ('Weapon 1', bow)}, rarity={'bow':'unique'})
out['partial_rarity'] = dict(base=bow, check_slots=report.decision(s.CHECK_SLOTS).value,
                            gaps=[g.gap_id for g in export.gaps], cited_gaps=report.cited_gap_ids)
changed = copy.deepcopy(probe)
for row in changed['slots']:
    if row['slot'] == 'Weapon 1':
        row['categories']['Bow']['accepted'] = 1
export = s._export(changed)
report = s._validate(export, {'bow': ('Weapon 1', bow)})
out['partial_category'] = dict(check_slots=report.decision(s.CHECK_SLOTS).value,
                               violation_codes=report.violation_codes,
                               gaps=[g.gap_id for g in export.gaps])
Path(sys.argv[2]).write_text(json.dumps(out, indent=2), encoding='utf-8')
print(json.dumps(out, indent=2))
