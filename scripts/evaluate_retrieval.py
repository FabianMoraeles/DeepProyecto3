"""Recall de tablas gold: solo evaluador, nunca entrega gold al recuperador."""
import argparse
from dataclasses import replace
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.catalog import catalog
from app.config import Config
from app.retrieval import retrieve
from datoclaro.data import load_split, public_request
from datoclaro.io import ROOT, write_json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--method',choices=['lexical','semantic'],default='lexical')
    args=parser.parse_args()
    results=[]
    for k in (2,4,6):
        cases=[]
        for row in load_split('dev'):
            # Aproximación léxica documentada: nombres de tablas después de FROM/JOIN.
            referenced={m.group(1).casefold() for m in re.finditer(r'\b(?:FROM|JOIN)\s+["`\[]?([\w]+)', row['gold_sql'], re.I)}
            known={t['name'].casefold() for t in catalog()[row['db_id']]['tables']}
            needed=referenced & known
            actual=set(t.casefold() for t in retrieve(public_request(row),Config(top_k=k,examples=0,retrieval=args.method))['tables'])
            cases.append({'id':row['id'],'needed':sorted(needed),'retrieved':sorted(actual),'recall':len(needed & actual)/len(needed) if needed else None})
        valid=[r['recall'] for r in cases if r['recall'] is not None]
        results.append({'k':k,'mean_table_recall':sum(valid)/len(valid),'n':len(valid),'cases':cases})
    write_json(ROOT/f'artifacts/retrieval_{args.method}.json',{'method':args.method,'gold_table_extraction':'lexical_from_join_approximation','results':results})
    for r in results: print(r['k'],r['mean_table_recall'],r['n'])


if __name__=='__main__': main()
