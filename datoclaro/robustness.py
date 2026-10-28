"""Evaluación separada de casos construidos y del control SQL."""
from collections import Counter
from .data import db_path
from .execution import execute
from .io import ROOT, read_jsonl, write_json


def run(predictions=None):
    cases = read_jsonl(ROOT / 'data/robustness.jsonl')
    outputs = {}
    if predictions:
        for row in read_jsonl(predictions):
            if row['id'] in outputs:
                raise ValueError('IDs duplicados en robustez')
            outputs[row['id']] = row
        if set(outputs) - {r['id'] for r in cases}:
            raise ValueError('IDs desconocidos en robustez')
    results = []
    for row in cases:
        if predictions:
            actual = outputs.get(row['id'], {}).get('status', 'missing')
            expected = row['expected']
            passed = actual == expected
            if 'expected_rows' in row:
                passed = passed and outputs.get(row['id'], {}).get('row_count') == row['expected_rows']
        elif 'sql' in row:
            output = execute(db_path('california_schools'), row['sql'], timeout=.1 if row['expected']=='timeout' else 5, max_rows=row.get('max_rows',10000))
            actual = output['status']
            expected = 'rejected' if row['expected'] == 'refused' else row['expected']
            passed = actual == expected
            if 'expected_rows' in row:
                passed = passed and len(output['rows']) == row['expected_rows']
        else:
            # SQL executor cannot evaluate intent/ambiguity or UI input behavior.
            continue
        results.append({'id': row['id'], 'category': row['category'], 'expected': expected, 'actual': actual, 'passed': passed})
    report = {'scope': 'pipeline_outputs' if predictions else 'sql_executor', 'n_evaluated': len(results), 'n_total_cases': len(cases), 'passed': sum(r['passed'] for r in results), 'by_category': {category: {'n': sum(r['category']==category for r in results), 'passed': sum(r['category']==category and r['passed'] for r in results)} for category in sorted({r['category'] for r in results})}, 'results': results}
    write_json(ROOT / 'artifacts' / ('robustness_pipeline.json' if predictions else 'robustness_sql.json'), report)
    return report
