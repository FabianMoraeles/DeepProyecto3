from __future__ import annotations

import importlib
import json
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from .baselines import RetrievalBaseline
from .data import db_path, load_split, public_request
from .execution import execute, REFERENCE_CLOCK
from .io import ROOT, digest, read_jsonl, write_json, write_jsonl
from .metrics import mcnemar, summary, result_equal


def references(rows, workers=4):
    def one(row):
        result = execute(db_path(row['db_id']), row['gold_sql'])
        return {'id': row['id'], 'db_id': row['db_id'], 'difficulty': row['difficulty'], **result}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, rows))


def evaluate(split, predictions=None, predictor=None, baseline=False, limit=None, language='en'):
    rows = load_split(split)
    if limit is not None:
        if limit < 1:
            raise ValueError('limit debe ser positivo')
        rows = rows[:limit]
    if language == 'es':
        import csv
        with (ROOT / 'data/spanish_review.csv').open(encoding='utf-8', newline='') as stream:
            translations = {r['id']: r for r in csv.DictReader(stream)}
        valid = []
        for row in rows:
            t = translations.get(row['id'], {})
            if t.get('reviewed', '').lower() == 'true' and t.get('question_es', '').strip() and t.get('reviewer', '').strip() and t.get('translator', '').strip():
                valid.append({**row, 'question': t['question_es'], 'language': 'es'})
        rows = valid
    if not rows:
        raise ValueError('No hay casos evaluables en ese split/idioma')
    # Resolve all DBs before charging any model calls.
    for row in rows:
        db_path(row['db_id'])
    candidates = {}
    function = None
    if baseline:
        function = RetrievalBaseline(load_split('kb')).predict
    elif predictor:
        module, name = predictor.split(':')
        function = getattr(importlib.import_module(module), name)
    elif predictions:
        for row in read_jsonl(predictions):
            if row['id'] in candidates:
                raise ValueError('Predicciones duplicadas')
            candidates[row['id']] = row
        if set(candidates) - {r['id'] for r in rows}:
            raise ValueError('Archivo contiene IDs ajenos al conjunto evaluado')
    else:
        raise ValueError('Indicar baseline, predictor o predicciones')
    scores, outputs = [], []
    for index, row in enumerate(rows):
        gold = execute(db_path(row['db_id']), row['gold_sql'])
        start = time.perf_counter()
        output = candidates.get(row['id'])
        if function:
            try:
                output = function(public_request(row))
                if not isinstance(output, dict):
                    raise TypeError('predict debe devolver dict')
            except Exception as exc:
                output = {'status': 'error', 'sql': '', 'error': str(exc)}
        generation_ms = (time.perf_counter() - start) * 1000 if function else (output or {}).get('latency_ms')
        if output is None:
            prediction = {'status': 'missing', 'rows': [], 'columns': [], 'elapsed_ms': 0, 'error': 'Predicción ausente'}
            output = {'sql': '', 'status': 'missing'}
        elif output.get('status', 'ok') != 'ok':
            prediction = {'status': output['status'], 'rows': [], 'columns': [], 'elapsed_ms': 0, 'error': output.get('error')}
        else:
            prediction = execute(db_path(row['db_id']), output.get('sql', ''))
        outputs.append({**output, 'id': row['id']})
        scores.append({
            'id': row['id'], 'group_id': row['group_id'], 'db_id': row['db_id'], 'difficulty': row['difficulty'], 'language': row['language'],
            'gold_status': gold['status'], 'gold_error': gold['error'], 'gold_rows': len(gold['rows']) if gold['status'] == 'ok' else None,
            'prediction_status': prediction['status'], 'prediction_error': prediction.get('error'),
            'correct': result_equal(gold, prediction, row['ordered']),
            'latency_ms': generation_ms + prediction['elapsed_ms'] if generation_ms is not None else None,
            **{key: output.get(key) for key in ('model', 'prompt_version', 'tokens_in', 'tokens_out', 'cost_usd')},
        })
        if (index + 1) % 25 == 0:
            print(f'Evaluados {index+1}/{len(rows)}', flush=True)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    out = ROOT / 'artifacts/runs' / run_id
    out.mkdir(parents=True, exist_ok=False)
    write_jsonl(out / 'predictions.jsonl', outputs)
    write_jsonl(out / 'scores.jsonl', scores)
    report = summary(scores)
    report['subgroups'] = {field: {value: summary([r for r in scores if r[field] == value]) for value in sorted({r[field] for r in scores})} for field in ('db_id', 'difficulty', 'language')}
    write_json(out / 'summary.json', report)
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = 'uncommitted'
    write_json(out / 'manifest.json', {
        'run_id': run_id, 'git_commit': commit, 'split': split, 'language': language,
        'config': 'B0' if baseline else predictor or 'predictions', 'limit': limit,
        'questions_sha256': digest(ROOT / 'data/questions.jsonl'), 'splits_sha256': digest(ROOT / 'data/splits.json'),
        'predictions_sha256': digest(out / 'predictions.jsonl'),
        'spanish_review_sha256': digest(ROOT / 'data/spanish_review.csv') if language == 'es' else None,
        'source_manifest_sha256': digest(ROOT / 'data/source_manifest.json'),
        'reference_clock': REFERENCE_CLOCK,
        'code_sha256': {str(p.relative_to(ROOT)): digest(p) for folder in ('datoclaro', 'app') for p in sorted((ROOT / folder).glob('*.py'))},
    })
    print(json.dumps({'run_dir': str(out), **{k: v for k, v in report.items() if k != 'subgroups'}}, indent=2))
    return out


def compare(run_a, run_b):
    a, b = Path(run_a), Path(run_b)
    ma, mb = [json.loads((path / 'manifest.json').read_text()) for path in (a, b)]
    for key in ('questions_sha256', 'splits_sha256', 'language', 'split', 'source_manifest_sha256', 'spanish_review_sha256', 'reference_clock'):
        if ma.get(key) != mb.get(key):
            raise ValueError(f'Corridas incompatibles: {key}')
    aa, bb = [{r['id']: r for r in read_jsonl(path / 'scores.jsonl')} for path in (a, b)]
    if set(aa) != set(bb):
        raise ValueError('Corridas deben contener exactamente los mismos IDs')
    ids = sorted(k for k in aa if aa[k]['gold_status'] == bb[k]['gold_status'] == 'ok')
    return {'n_paired': len(ids), **mcnemar([aa[k]['correct'] for k in ids], [bb[k]['correct'] for k in ids])}
