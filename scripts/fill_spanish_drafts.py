"""Rellena borradores de traducción sin atribuir revisión humana."""
import csv
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / 'data/spanish_review.csv'
drafts = json.loads((root / 'data/spanish_drafts.json').read_text(encoding='utf-8'))
with path.open(encoding='utf-8', newline='') as stream:
    reader = csv.DictReader(stream)
    fields = reader.fieldnames
    rows = list(reader)
for row in rows:
    if not row['question_es'] and row['id'] in drafts:
        row['question_es'] = drafts[row['id']]
        row['translator'] = 'AI draft'
        row['reviewed'] = 'false'
with path.open('w', encoding='utf-8', newline='') as stream:
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
print(f'{sum(bool(r["question_es"]) for r in rows)} borradores; revisión humana no declarada')
