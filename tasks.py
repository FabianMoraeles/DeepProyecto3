#!/usr/bin/env python3
"""Comandos reproducibles para Windows, macOS y Linux."""
import argparse
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

from datoclaro.data import fetch, load_split, translation_template, validate
from datoclaro.io import ROOT, read_jsonl, write_json, write_jsonl


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='task', required=True)
    for name in ('fetch-data', 'check-data', 'eda', 'translation-template', 'test'):
        sub.add_parser(name)
    refs = sub.add_parser('check-references')
    refs.add_argument('--workers', type=int, default=4)
    ev = sub.add_parser('eval')
    ev.add_argument('--split', choices=['dev', 'test'], default='dev')
    ev.add_argument('--language', choices=['en', 'es'], default='en')
    ev.add_argument('--limit', type=int)
    source = ev.add_mutually_exclusive_group(required=True)
    source.add_argument('--baseline', action='store_true')
    source.add_argument('--predictions', type=Path)
    source.add_argument('--predictor', help='module:function')
    comp = sub.add_parser('compare')
    comp.add_argument('run_a')
    comp.add_argument('run_b')
    figures = sub.add_parser('figures')
    figures.add_argument('runs', nargs='+', type=Path)
    robust = sub.add_parser('robustness')
    robust.add_argument('--predictions', type=Path)
    args = parser.parse_args()
    if args.task == 'fetch-data':
        fetch()
    elif args.task == 'check-data':
        rows = read_jsonl(ROOT / 'data/questions.jsonl')
        validate(rows)
        sizes = {s: len(load_split(s)) for s in ('kb', 'dev', 'test')}
        from datoclaro.data import db_path
        from datoclaro.io import digest
        manifest = json.loads((ROOT / 'data/source_manifest.json').read_text())
        for database, expected in manifest['database_files'].items():
            if digest(db_path(database)) != expected:
                raise ValueError(f'La base cambió: {database}')
        print(json.dumps({'rows': len(rows), 'splits': sizes, 'databases_verified': len(manifest['database_files'])}, indent=2))
    elif args.task == 'translation-template':
        translation_template()
    elif args.task == 'check-references':
        from datoclaro.evaluation import references
        results = references(read_jsonl(ROOT / 'data/questions.jsonl'), args.workers)
        # Avoid publishing answer rows; report status and cardinality only.
        rows = [{k: v for k, v in r.items() if k not in {'rows', 'columns'}} | {'row_count': len(r['rows']) if r['status'] == 'ok' else None} for r in results]
        write_jsonl(ROOT / 'artifacts/reference_audit.jsonl', rows)
        report = {'n': len(rows), 'statuses': dict(Counter(r['status'] for r in rows))}
        write_json(ROOT / 'artifacts/reference_summary.json', report)
        print(json.dumps(report, indent=2))
        if report['statuses'].get('ok', 0) != len(rows):
            return 1
    elif args.task == 'eda':
        rows = read_jsonl(ROOT / 'data/questions.jsonl')
        report = {'n': len(rows), 'by_database': dict(Counter(r['db_id'] for r in rows)), 'by_difficulty': dict(Counter(r['difficulty'] for r in rows)), 'question_characters': {'min': min(len(r['question']) for r in rows), 'max': max(len(r['question']) for r in rows)}, 'split_counts': {s: len(load_split(s)) for s in ('kb', 'dev', 'test')}}
        write_json(ROOT / 'artifacts/eda.json', report)
        print(json.dumps(report, indent=2))
    elif args.task == 'eval':
        from datoclaro.evaluation import evaluate
        evaluate(args.split, args.predictions, args.predictor, args.baseline, args.limit, args.language)
    elif args.task == 'compare':
        from datoclaro.evaluation import compare
        print(json.dumps(compare(args.run_a, args.run_b), indent=2))
    elif args.task == 'figures':
        from datoclaro.reports import figures
        figures(args.runs)
    elif args.task == 'robustness':
        from datoclaro.robustness import run
        result = run(args.predictions)
        print(json.dumps(result, indent=2))
        return int(result['passed'] != result['n_evaluated'])
    elif args.task == 'test':
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT / 'tests')))
        return 0 if result.wasSuccessful() else 1
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, FileNotFoundError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        raise SystemExit(1)
