"""Recuperación por tabla y ejemplos kb, con puentes de claves foráneas."""
from collections import deque
from functools import lru_cache
import math
import re
from datoclaro.baselines import words
from datoclaro.data import load_split
from datoclaro.io import ROOT
from .catalog import catalog

ALIASES = {'escuelas': 'schools school', 'escuela': 'school', 'condados': 'county',
           'matricula': 'enrollment', 'miembros': 'member', 'eventos': 'event attendance',
           'presupuesto': 'budget amount', 'gastos': 'expense spent', 'carrera': 'major',
           'matematicas': 'math satscores', 'ingresos': 'income', 'prestamos': 'loan'}
EMBEDDING_REVISION = '614241f622f53c4eeff9890bdc4f31cfecc418b3'


def lexical_scores(query, documents):
    terms = words(query)
    expanded = terms + words(' '.join(ALIASES.get(w, '') for w in terms))
    sets = [set(words(d)) for d in documents]
    return [sum(math.log((len(sets)+1)/(1+sum(w in s for s in sets)))+1
                for w in set(expanded) if w in doc) / math.sqrt(max(1, len(doc))) for doc in sets]


@lru_cache(maxsize=1)
def encoder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer('intfloat/multilingual-e5-small', revision=EMBEDDING_REVISION,
                               cache_folder=str(ROOT/'artifacts/huggingface/hub'), device='cpu')


@lru_cache(maxsize=32)
def embeddings(documents):
    return encoder().encode(['passage: '+d for d in documents], normalize_embeddings=True)


def rank(query, documents, method):
    if not documents:
        return []
    if method == 'semantic':
        vector = encoder().encode(['query: '+query], normalize_embeddings=True)[0]
        scores = embeddings(tuple(documents)) @ vector
    elif method == 'lexical':
        scores = lexical_scores(query, documents)
    else:
        raise ValueError('Recuperación desconocida')
    return sorted(range(len(documents)), key=lambda i: (-float(scores[i]), i))


@lru_cache(maxsize=1)
def knowledge():
    return load_split('kb')


def bridge_tables(selected, tables):
    graph = {t['name']: set() for t in tables}
    for t in tables:
        for fk in t['foreign_keys']:
            if fk['table'] in graph:
                graph[t['name']].add(fk['table'])
                graph[fk['table']].add(t['name'])
    result = set(selected)
    for source in sorted(selected):
        for target in sorted(selected):
            queue, seen = deque([(source, [source])]), {source}
            while queue:
                node, path = queue.popleft()
                if node == target:
                    result.update(path)
                    break
                for nxt in sorted(graph[node] - seen):
                    seen.add(nxt)
                    queue.append((nxt, path+[nxt]))
    return [t for t in tables if t['name'] in result]


def table_document(table):
    # Compact DDL keeps every column, type and FK; never includes table rows.
    cols = ', '.join('"'+c['name'].replace('"','""')+'" '+c['type']+(' PRIMARY KEY' if c['primary_key'] else '') for c in table['columns'])
    fks = '; '.join(f"{f['from']} -> {f['table']}.{f['to']}" for f in table['foreign_keys'])
    return f"TABLE {table['name']} ({cols})\nRELATIONS {fks}"


def retrieve(request, config):
    tables = catalog()[request['db_id']]['tables']
    order = rank(request['question'], [table_document(t) for t in tables], config.retrieval)
    selected = tables if config.full_schema else bridge_tables({tables[i]['name'] for i in order[:config.top_k]}, tables)
    candidates = [r for r in knowledge() if r['db_id'] == request['db_id'] and r['id'] != request.get('id')]
    indexes = rank(request['question'], [r['question'] for r in candidates], config.retrieval) if config.examples else []
    examples = [{'id': candidates[i]['id'], 'question': candidates[i]['question'], 'sql': candidates[i]['gold_sql']} for i in indexes[:config.examples]]
    return {'schema': '\n\n'.join(table_document(t) for t in selected), 'tables': [t['name'] for t in selected],
            'examples': examples, 'method': config.retrieval,
            'embedding_revision': EMBEDDING_REVISION if config.retrieval == 'semantic' else None}
