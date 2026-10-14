"""Independent offline PR10 review observations; no network or engine.

Run from any directory. The temporary corpus is discarded after observation.
These are probes, not tests endorsing the observed defects.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for directory in (ROOT / 'pob2-mcp', ROOT / 'pob2-optimizer', ROOT / 'tests', ROOT / 'tests/unit'):
    sys.path.insert(0, str(directory))

import p04_fixtures as fx
from pob2opt import cli
from pob2opt.domain.absent import ABSENT
from pob2opt.domain.identity import build_hash
from pob2opt.domain.migrate import upgrade_build_spec
from pob2opt.domain.records import BuildSpec
from pob2opt.evaluation import export_build
from pob2opt.parsers import parse_document
from pob2opt.parsers.corpus import audit_variant
from pob2opt.parsers.resolve import class_for_document_name, migrate_build, naming_from_catalog
from pob2opt.storage import RunStore
from test_p04_parse_cli import ingest, merged_rows


def naming(data):
    class_id = class_for_document_name(fx.entities(), ET.fromstring(data).find('Build').get('className'))
    return naming_from_catalog(fx.entities(), class_id=class_id).naming


def parse(data, context=None):
    return parse_document(fx.source(data), data, context or fx.context())


def summarize(outcome, data):
    items = {i.item_hash: i for i in outcome.items}
    return {
        'result_status': outcome.result.status.value,
        'issues': [i.code for i in outcome.result.issues],
        'build_statuses': [b.parse_status.value for b in outcome.builds],
        'item_statuses': [i.parse_status.value for i in outcome.items],
        'recommended_exports': [export_build(b, items, naming(data)).recommended_deliverable for b in outcome.builds],
    }


def main():
    observed = {}
    data = fx.document_bytes('b01')
    root = ET.fromstring(data)
    item = root.find('Items/Item')
    item.text = item.text.rstrip() + '\nSYNTHETIC +3 to unknown things\n'
    changed = ET.tostring(root, encoding='utf-8')
    observed['unresolved_affix'] = summarize(parse(changed), changed)

    root = ET.fromstring(data)
    item = root.find('Items/Item')
    lines = [line.strip() for line in item.text.splitlines() if line.strip()]
    item.text = '\n'.join(lines[:3]) + '\n'
    changed = ET.tostring(root, encoding='utf-8')
    observed['name_only_equipped_item'] = summarize(parse(changed), changed)

    for label, change in (
        ('invalid_level', lambda r: r.find('Build').set('level', 'not-a-number')),
        ('invalid_node', lambda r: r.find('Tree/Spec').set('nodes', 'broken')),
        ('invalid_active_gem_level', lambda r: r.find('Skills/SkillSet/Skill/Gem').set('level', 'broken')),
    ):
        root = ET.fromstring(data)
        change(root)
        payload = ET.tostring(root, encoding='utf-8')
        try:
            result = parse(payload)
            observed[label] = {'status': result.result.status.value}
        except Exception as exc:
            observed[label] = {'raised': type(exc).__name__, 'message': str(exc)}

    root = ET.fromstring(data)
    support = next(s for g in parse(data).builds[0].skill_groups for sk in g.skills for s in sk.supports)
    target = dict(fx.entities())
    target['gems'] = [e for e in target['gems'] if e.entity_id != support.gem_id]
    migrated = migrate_build(parse(data).builds[0], fx.entities(), target,
                             target_catalog_hash='1' * 64, record_id='review/migrated', created_at=fx.CREATED_AT)
    observed['removed_support_gem'] = {
        'removed_gem': support.gem_id,
        'reported_removals': [c.entity_id for c in migrated.removed],
        'status': migrated.build.parse_status.value,
        'unresolved': [r.reference for r in migrated.build.unresolved_refs],
    }

    # Version 1 has two explicitly selected groups and no supports. Its own
    # exporter is the oracle for the migration's stated compatibility promise.
    data = fx.document_bytes('b03')
    outcome = parse(data)
    build = outcome.builds[0]
    groups = [replace(g, main_skill_index=0,
                      skills=[replace(s, support_ids=[], supports=ABSENT) for s in g.skills])
              for g in build.skill_groups]
    legacy = replace(build, schema_version=1, main_skill_group=ABSENT,
                     skill_groups=groups)
    legacy = replace(legacy, build_hash=build_hash(legacy))
    upgraded = upgrade_build_spec(legacy, record_id='review/v2', created_at=fx.CREATED_AT)
    items = {i.item_hash: i for i in outcome.items}
    observed['v1_main_group_migration'] = {
        'v1_export_main': ET.fromstring(export_build(legacy, items, naming(data)).xml).find('Build').get('mainSocketGroup'),
        'v2_export_main': ET.fromstring(export_build(upgraded, items, naming(data)).xml).find('Build').get('mainSocketGroup'),
    }

    # A different valid selected main group is invisible to the field audit.
    data = fx.document_bytes('b03')
    outcome = parse(data)
    build = outcome.builds[0]
    altered = replace(build, main_skill_group=1 - build.main_skill_group)
    altered = replace(altered, build_hash=build_hash(altered))
    audit = audit_variant(data.decode(), outcome.split.variants[0].selection,
                          altered, {i.item_hash: i for i in outcome.items}, naming(data))
    observed['audit_changed_main_group'] = {'passed': audit.passed, 'mismatches': len(audit.mismatches),
                                           'source_main': build.main_skill_group,
                                           'changed_main': altered.main_skill_group}

    # Exercise the actual comparison used for engine evidence without PoB.
    spec = importlib.util.spec_from_file_location('pr10_engine_checks', ROOT / 'tests/engine/test_p04_round_trips.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    observed['engine_comparator'] = {
        'zero_to_nonzero': module._stat_differences({'Damage': 0}, {'Damage': 1000}),
        'added_numeric_stat': module._stat_differences({'Damage': 10}, {'Damage': 10, 'BonusDamage': 1000}),
    }

    # Two genuinely distinct exported catalog bundles, one corpus/source.
    with tempfile.TemporaryDirectory(prefix='pr10-review-') as temp:
        temp = Path(temp)
        rows_path = merged_rows(temp / 'rows.json')
        rows = json.loads(rows_path.read_text(encoding='utf-8'))
        a, b = temp / 'catalog-a', temp / 'catalog-b'
        evidence = ROOT / 'docs/evidence/P02'
        def command(args):
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = cli.main(args)
            return code, stdout.getvalue(), stderr.getvalue()
        for bundle in (a, b):
            if bundle == b:
                rows['tables']['granted_skills'] = []
                rows_path.write_text(json.dumps(rows), encoding='utf-8')
            code, _, err = command(['catalog', 'export', '--profile', str(evidence / 'catalog-profile-request.json'),
                                    '--out', str(bundle), '--rows', str(rows_path), '--release-evidence', str(evidence / 'release')])
            assert code == 0, err
        corpus = temp / 'corpus'
        source_id = ingest(corpus, 'b03')
        reports = []
        for bundle in (a, b):
            code, stdout, err = command(['parse', '--source', source_id, '--corpus', str(corpus), '--catalog', str(bundle)])
            report = json.loads(stdout)
            with RunStore.open_corpus(corpus) as store:
                builds = [store.get_record(r) for r in report['record_ids']]
                builds = [r for r in builds if isinstance(r, BuildSpec)]
            reports.append({'code': code, 'status': report['status'], 'unchanged': report['unchanged'],
                            'requested_catalog': json.loads((bundle / 'catalog.json').read_text())['catalog_hash'],
                            'returned_build_catalogs': [x.catalog_hash for x in builds], 'result_id': report['parse_result_id']})
        observed['catalog_cache'] = reports
        # A fresh parse under catalog B confirms this is materially different.
        from pob2opt.parsers.cli import _load_catalog
        catalog = _load_catalog(b)[0]
        fresh = parse(fx.document_bytes('b03'), fx.context(catalog_hash=catalog.catalog_hash, entities=catalog.entities))
        observed['catalog_b_fresh'] = {'status': fresh.result.status.value,
                                      'build_statuses': [x.parse_status.value for x in fresh.builds]}
    print(json.dumps(observed, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
