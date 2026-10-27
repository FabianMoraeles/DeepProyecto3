from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import shutil
import sqlite3
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

from .execution import ordered_query
from .io import ROOT, digest, read_jsonl, write_json, write_jsonl

REVISION = '1bc27809bb190647e0236e8dc08aae78ab2b48c1'
QUESTIONS_URL = f'https://huggingface.co/datasets/birdsql/bird_mini_dev/resolve/{REVISION}/archive/bird_mini_dev_2025-07-04/data/mini_dev_sqlite-00000-of-00001.json'
QUESTIONS_SHA = '88ceb0710163cae46a256ecea8f0a8c98286599530b60587fda5c3cfe57d45d2'
DATABASE_URL = 'https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip'
DATABASE_SHA = 'cdd6d19faeb45a23970b98d3ef6c40a87987c95459c2cf12076897a60cf5a630'
SOURCE = 'https://huggingface.co/datasets/birdsql/bird_mini_dev'


def download(url, path, expected):
    path = Path(path)
    if path.is_file() and expected and digest(path) == expected:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.part')
    with urllib.request.urlopen(url, timeout=120) as remote, temporary.open('wb') as local:
        shutil.copyfileobj(remote, local)
    if expected and digest(temporary) != expected:
        raise ValueError(f'Integridad incorrecta: {path}; archivo conservado en {temporary}')
    temporary.replace(path)


def group_id(row):
    # Preserve literals/case: normalization must not change SQL semantics.
    normalized = row['gold_sql'].strip().rstrip(';').strip()
    return hashlib.sha256((row['db_id'] + '\0' + normalized).encode()).hexdigest()[:20]


def normalize(raw):
    rows = []
    for item in raw:
        row = {
            'id': f"bird-{item['question_id']:03d}", 'db_id': item['db_id'],
            'question': item['question'], 'language': 'en',
            'evidence': item.get('evidence', ''), 'gold_sql': item['SQL'],
            'difficulty': item['difficulty'], 'ordered': ordered_query(item['SQL']),
            'source': SOURCE,
        }
        row['group_id'] = group_id(row)
        rows.append(row)
    validate(rows)
    return rows


def validate(rows):
    if not rows:
        raise ValueError('Dataset vacío')
    ids = set()
    for row in rows:
        for field in ('id', 'db_id', 'question', 'language', 'gold_sql', 'difficulty', 'source', 'group_id'):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f'Campo inválido {field}: {row.get("id")}')
        if row['id'] in ids:
            raise ValueError(f'ID duplicado: {row["id"]}')
        ids.add(row['id'])
        if not re.fullmatch(r'[a-zA-Z0-9_]+', row['db_id']):
            raise ValueError('db_id inválido')
        if row['difficulty'] not in {'simple', 'moderate', 'challenging'}:
            raise ValueError('Dificultad desconocida')
        if row['language'] not in {'en', 'es'} or not isinstance(row.get('ordered'), bool):
            raise ValueError('Idioma/orden inválido')


def make_splits(rows, seed=3092):
    validate(rows)
    buckets = defaultdict(dict)
    for row in rows:
        key = (row['db_id'], row['difficulty'])
        buckets[key].setdefault(row['group_id'], []).append(row['id'])
    assignment = {}
    rng = random.Random(seed)
    splits = {'kb': [], 'dev': [], 'test': []}
    weights = {'kb': .35, 'dev': .20, 'test': .45}
    for key in sorted(buckets):
        groups = list(buckets[key].items())
        rng.shuffle(groups)
        groups.sort(key=lambda pair: len(pair[1]), reverse=True)
        total = sum(len(ids) for _, ids in groups)
        counts = dict.fromkeys(weights, 0)
        for group, ids in groups:
            selected = assignment.get(group) or max(weights, key=lambda s: weights[s] * total - counts[s])
            assignment[group] = selected
            splits[selected].extend(ids)
            counts[selected] += len(ids)
    for ids in splits.values():
        ids.sort()
    return {'seed': seed, 'proportions': weights, 'splits': splits}


def check_splits(rows, payload):
    lookup = {r['id']: r for r in rows}
    all_ids = [x for ids in payload['splits'].values() for x in ids]
    if len(set(all_ids)) != len(all_ids) or set(all_ids) != set(lookup):
        raise ValueError('Los splits no son una partición exacta')
    seen = {}
    for split, ids in payload['splits'].items():
        for id_ in ids:
            group = lookup[id_]['group_id']
            if group in seen and seen[group] != split:
                raise ValueError('Fuga de grupo entre splits')
            seen[group] = split


def db_path(db_id, directory=ROOT / 'data/databases'):
    if not re.fullmatch(r'[A-Za-z0-9_]+', db_id):
        raise ValueError('db_id fuera del catálogo')
    path = Path(directory) / db_id / f'{db_id}.sqlite'
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def extract_databases(archive, ids, destination):
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            parts = PurePosixPath(member.filename).parts
            if '..' in parts or member.is_dir() or member.file_size > 2_000_000_000:
                continue
            for database in ids:
                if database not in parts:
                    continue
                pos = parts.index(database)
                relative = PurePosixPath(*parts[pos:])
                if relative.name != f'{database}.sqlite' and not ('database_description' in relative.parts and relative.suffix == '.csv'):
                    continue
                target = Path(destination).joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(member) as source, target.open('wb') as out:
                    shutil.copyfileobj(source, out)


def schema(database, directory=ROOT / 'data/databases'):
    connection = sqlite3.connect(db_path(database, directory).resolve().as_uri() + '?mode=ro', uri=True)
    tables = []
    try:
        for (table, ddl) in connection.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            quoted = '"' + table.replace('"', '""') + '"'
            columns = [{'name': c[1], 'type': c[2], 'not_null': bool(c[3]), 'primary_key': bool(c[5])} for c in connection.execute(f'PRAGMA table_info({quoted})')]
            keys = [{'table': k[2], 'from': k[3], 'to': k[4]} for k in connection.execute(f'PRAGMA foreign_key_list({quoted})')]
            tables.append({'name': table, 'ddl': ddl, 'columns': columns, 'foreign_keys': keys})
    finally:
        connection.close()
    return {'db_id': database, 'tables': tables}


def fetch():
    raw = ROOT / 'data/raw'
    download(QUESTIONS_URL, raw / 'bird_questions_2025.jsonl', QUESTIONS_SHA)
    download(DATABASE_URL, raw / 'bird_dev.zip', DATABASE_SHA)
    rows = normalize(json.loads((raw / 'bird_questions_2025.jsonl').read_text(encoding='utf-8')))
    if len(rows) != 500:
        raise ValueError('Se esperaban 500 preguntas SQLite')
    output = ROOT / 'data/questions.jsonl'
    # Never silently overwrite curated data.
    if output.exists() and read_jsonl(output) != rows:
        raise ValueError('questions.jsonl contiene modificaciones: conservarlo antes de regenerar')
    ids = sorted({r['db_id'] for r in rows})
    with zipfile.ZipFile(raw / 'bird_dev.zip') as archive:
        with archive.open('dev_20240627/dev_databases.zip') as source, (raw / 'dev_databases.zip').open('wb') as target:
            shutil.copyfileobj(source, target)
    extract_databases(raw / 'dev_databases.zip', ids, ROOT / 'data/databases')
    write_jsonl(output, rows)
    split_data = make_splits(rows)
    check_splits(rows, split_data)
    split_data['dataset_sha256'] = digest(output)
    write_json(ROOT / 'data/splits.json', split_data)
    write_jsonl(ROOT / 'data/schemas.jsonl', [schema(id_) for id_ in ids])
    write_json(ROOT / 'data/source_manifest.json', {
        'source': SOURCE, 'revision': REVISION, 'edition': '2025-07-04', 'license': 'CC BY-SA 4.0',
        'questions_url': QUESTIONS_URL, 'questions_sha256': digest(raw / 'bird_questions_2025.jsonl'),
        'databases_url': DATABASE_URL, 'databases_sha256': digest(raw / 'bird_dev.zip'),
        'rows': len(rows), 'db_ids': ids,
        'database_files': {id_: digest(db_path(id_)) for id_ in ids},
        'transformations': ['Stable bird-NNN IDs', 'Preserved English question/evidence/gold SQL', 'Computed outer ORDER BY flag', 'Grouped identical queries per database'],
    })
    print(json.dumps({'rows': len(rows), 'databases': len(ids), 'splits': {s: len(v) for s, v in split_data['splits'].items()}}, indent=2))


def load_split(name, questions=ROOT / 'data/questions.jsonl', splits=ROOT / 'data/splits.json'):
    rows = read_jsonl(questions)
    validate(rows)
    payload = json.loads(Path(splits).read_text(encoding='utf-8'))
    if payload.get('dataset_sha256') != digest(questions):
        raise ValueError('El dataset cambió después de congelar los splits')
    check_splits(rows, payload)
    ids = set(payload['splits'][name])
    return [r for r in rows if r['id'] in ids]


def public_request(row):
    return {key: row[key] for key in ('id', 'db_id', 'question', 'language')}


def translation_template():
    rows = read_jsonl(ROOT / 'data/questions.jsonl')
    primary = [r for r in rows if r['db_id'] in {'california_schools', 'student_club'}]
    other = [r for r in rows if r not in primary]
    selected = primary + sorted(other, key=lambda r: hashlib.sha256(r['id'].encode()).hexdigest())[:max(0, 120-len(primary))]
    path = ROOT / 'data/spanish_review.csv'
    if path.exists():
        raise ValueError('Existe spanish_review.csv; no se sobrescribe trabajo de revisión')
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['id', 'db_id', 'question_en', 'question_es', 'translator', 'reviewer', 'reviewed'])
        writer.writeheader()
        for r in selected:
            writer.writerow({'id': r['id'], 'db_id': r['db_id'], 'question_en': r['question'], 'reviewed': 'false'})
    print(f'{len(selected)} filas para revisión española: {path}')
