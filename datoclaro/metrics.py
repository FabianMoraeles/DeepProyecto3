"""Comparación de resultados, IC bootstrap y prueba pareada exacta."""
from __future__ import annotations

import math
import random
from collections import Counter


def equal_cell(a, b):
    if a is None or b is None:
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6)
    return type(a) is type(b) and a == b


def equal_row(a, b):
    return len(a) == len(b) and all(equal_cell(x, y) for x, y in zip(a, b))


def result_equal(gold, prediction, ordered=False):
    if gold['status'] != 'ok' or prediction['status'] != 'ok':
        return False
    a, b = gold['rows'], prediction['rows']
    if len(gold['columns']) != len(prediction['columns']) or len(a) != len(b):
        return False
    if ordered:
        return all(equal_row(x, y) for x, y in zip(a, b))
    # Sorting preserves duplicates. Pairwise matching within equal rows avoids
    # dropping multiplicity as a set-based comparison would.
    def key(row):
        return tuple((0, '') if x is None else (1, float(x)) if isinstance(x, (int, float)) else (2, str(x)) for x in row)
    return all(equal_row(x, y) for x, y in zip(sorted(a, key=key), sorted(b, key=key)))


def percentile(values, q):
    if not values:
        return None
    values = sorted(values)
    pos = (len(values) - 1) * q
    low = math.floor(pos)
    high = math.ceil(pos)
    return values[low] + (values[high] - values[low]) * (pos - low)


def bootstrap(values, seed=3092, iterations=1000):
    if not values:
        return [None, None]
    rng = random.Random(seed)
    means = [sum(rng.choices(values, k=len(values))) / len(values) for _ in range(iterations)]
    return [percentile(means, .025), percentile(means, .975)]


def summary(rows):
    valid = [r for r in rows if r['gold_status'] == 'ok']
    scores = [int(r['correct']) for r in valid]
    groups = {}
    for row in valid:
        groups.setdefault(row.get('group_id', row['id']), []).append(int(row['correct']))
    # Cluster bootstrap: all related queries are sampled as one unit.
    rng = random.Random(3092)
    clusters = list(groups.values())
    means = []
    if clusters:
        for _ in range(1000):
            sample = [x for cluster in rng.choices(clusters, k=len(clusters)) for x in cluster]
            means.append(sum(sample) / len(sample))
    latencies = [r['latency_ms'] for r in rows if r.get('latency_ms') is not None]
    costs = [r['cost_usd'] for r in rows if r.get('cost_usd') is not None]
    return {
        'n': len(rows), 'reference_valid': len(valid),
        'reference_coverage': len(valid) / len(rows) if rows else None,
        'execution_accuracy': sum(scores) / len(scores) if scores else None,
        'correct_over_all_cases': sum(scores) / len(rows) if rows else None,
        'accuracy_ci95': [percentile(means, .025), percentile(means, .975)],
        'executable_rate': sum(r['prediction_status'] == 'ok' for r in rows) / len(rows) if rows else None,
        'prediction_statuses': dict(Counter(r['prediction_status'] for r in rows)),
        'latency_p50_ms': percentile(latencies, .5), 'latency_p95_ms': percentile(latencies, .95),
        'cost_observed_n': len(costs), 'cost_observed_total_usd': sum(costs) if costs else None,
        'tokens_in_observed': sum(r.get('tokens_in') or 0 for r in rows) if any(r.get('tokens_in') is not None for r in rows) else None,
        'tokens_out_observed': sum(r.get('tokens_out') or 0 for r in rows) if any(r.get('tokens_out') is not None for r in rows) else None,
        'empty_gold_n': sum(r.get('gold_rows') == 0 for r in valid),
    }


def mcnemar(a, b):
    if len(a) != len(b) or not a:
        raise ValueError('Comparación requiere mismos casos no vacíos')
    a_only = sum(bool(x) and not y for x, y in zip(a, b))
    b_only = sum(bool(y) and not x for x, y in zip(a, b))
    n = a_only + b_only
    p = min(1.0, 2 * sum(math.comb(n, k) for k in range(min(a_only, b_only) + 1)) / 2**n) if n else 1.0
    return {'a_only': a_only, 'b_only': b_only, 'p_value': p}
