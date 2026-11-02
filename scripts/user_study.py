"""Analiza mediciones humanas; nunca genera participantes ni respuestas."""
import argparse
import csv
import json
from pathlib import Path
import statistics


def analyze(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as handle:
        rows=list(csv.DictReader(handle))
    if not rows: raise ValueError('El archivo no contiene mediciones.')
    seen=set(); people=[]
    for r in rows:
        identifier=r['participant_id'].strip()
        if not identifier or identifier in seen: raise ValueError('IDs vacíos o duplicados')
        seen.add(identifier)
        manual,assisted=float(r['manual_seconds']),float(r['assisted_seconds'])
        if min(manual,assisted)<=0: raise ValueError('Tiempos deben ser positivos')
        answers=[int(r['sus_'+str(i)]) for i in range(1,11)]
        if any(a not in range(1,6) for a in answers): raise ValueError('SUS requiere enteros 1–5')
        correctness=[int(r[k]) for k in ('manual_correct','assisted_correct')]
        if any(v not in (0,1) for v in correctness): raise ValueError('Aciertos deben ser 0 o 1')
        sus=2.5*sum(a-1 if i%2==0 else 5-a for i,a in enumerate(answers))
        people.append({'participant_id':identifier,'time_improvement':1-assisted/manual,'sus':sus,'manual_correct':correctness[0],'assisted_correct':correctness[1]})
    return {'n':len(people),'mean_sus':statistics.mean(p['sus'] for p in people),'mean_time_improvement':statistics.mean(p['time_improvement'] for p in people),
            'manual_accuracy':statistics.mean(p['manual_correct'] for p in people),'assisted_accuracy':statistics.mean(p['assisted_correct'] for p in people),'participants':people}


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('csv'); args=parser.parse_args()
    print(json.dumps(analyze(args.csv),ensure_ascii=False,indent=2))
