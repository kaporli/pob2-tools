"""PR10 repair review: replay old probes without overwriting their evidence.

Default: offline observations, including the remaining standalone-item and
numeric-boundary cases. --engine: run the old independent engine probe with
its output directory redirected here; use the bounded monitor alongside it.
"""
from __future__ import annotations
import contextlib
import faulthandler
import importlib.util
import io
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
for path in (ROOT / 'pob2-mcp', ROOT / 'pob2-optimizer', ROOT / 'tests'):
    sys.path.insert(0, str(path))


def offline():
    old = OUT.parent / 'review_adversarial.py'
    # Only the test helper's name changed; keep the original observations.
    code = old.read_text(encoding='utf-8').replace('module._stat_differences', 'module.stat_differences')
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        exec(compile(code, str(old), 'exec'), {'__file__': str(old), '__name__': '__main__'})
    original = json.loads(captured.getvalue())
    import p04_fixtures as fx
    from pob2opt.parsers import parse_document, naming_from_catalog
    from pob2opt.evaluation import export_build
    from pob2opt.evaluation.itemtext import export_item
    from pob2opt.parsers.resolve import class_for_document_name
    from pob2opt.domain.validation import validate_record

    root = ET.fromstring(fx.document_bytes('b01'))
    item = root.find('Items/Item')
    item.text = item.text.rstrip() + '\nSYNTHETIC +3 to unknown things\n'
    same_item = {}
    for kind, data in [('pob_xml', ET.tostring(root)), ('item_text', item.text.strip().encode())]:
        outcome = parse_document(fx.source(data), data, fx.context())
        subject = next(i for i in outcome.items if any('SYNTHETIC' in m.text for m in i.modifiers))
        _, losses = export_item(subject, naming_from_catalog(fx.entities()).naming)
        same_item[kind] = {'parse_status': outcome.result.status.value,
                           'item_status': subject.parse_status.value,
                           'issues': [i.code for i in outcome.result.issues],
                           'export_complete': losses.report().complete}

    numeric = {}
    for case in ('overflow_config', 'invalid_quality', 'negative_item_level'):
        root = ET.fromstring(fx.document_bytes('b01'))
        if case == 'overflow_config':
            ET.SubElement(root.find('Config/ConfigSet'), 'Input', {'name': 'enemyLevel', 'number': '1e999'})
        else:
            item = root.find('Items/Item')
            item.text += '\n' + ('Quality: broken' if case == 'invalid_quality' else 'Item Level: -1') + '\n'
        data = ET.tostring(root)
        try:
            outcome = parse_document(fx.source(data), data, fx.context())
            class_id = class_for_document_name(fx.entities(), root.find('Build').get('className'))
            naming = naming_from_catalog(fx.entities(), class_id=class_id).naming
            items = {i.item_hash: i for i in outcome.items}
            numeric[case] = {'parse_status': outcome.result.status.value,
                             'issues': [i.code for i in outcome.result.issues],
                             'item_properties': [i.properties for i in outcome.items],
                             'item_levels': [i.item_level for i in outcome.items],
                             'item_validation': [validate_record(i).ok for i in outcome.items],
                             'recommended_exports': [export_build(b, items, naming).recommended_deliverable for b in outcome.builds]}
        except Exception as error:
            numeric[case] = {'exception': type(error).__name__, 'message': str(error)}
    print(json.dumps({'original_probes': original, 'same_unknown_item': same_item,
                      'numeric_boundaries': numeric}, indent=2, sort_keys=True))


def engine():
    path = OUT.parent / 'review_engine.py'
    spec = importlib.util.spec_from_file_location('old_engine_review', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUT = OUT
    fault_path = ROOT / 'runs/pr10-followup-native.log'
    fault_path.parent.mkdir(parents=True, exist_ok=True)
    with fault_path.open('w') as log:
        faulthandler.enable(file=log)
        try:
            module.main()
        finally:
            faulthandler.disable()


if __name__ == '__main__':
    engine() if '--engine' in sys.argv else offline()
