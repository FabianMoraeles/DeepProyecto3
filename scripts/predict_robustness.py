"""Genera salidas reales de robustez sin exponer expectativas al modelo."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.pipeline import predict
from app.config import Config
from datoclaro.io import ROOT, read_jsonl, write_jsonl


if __name__=='__main__':
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    parser=argparse.ArgumentParser(); parser.add_argument('--output',default='artifacts/robust_predictions.jsonl'); args=parser.parse_args()
    results=[]
    for case in read_jsonl(ROOT/'data/robustness.jsonl'):
        output=predict({'id':case['id'],'db_id':'california_schools','question':case['question'],'language':'es'})
        execution=output.get('result',{})
        # Preserva timeout/row_limit en el protocolo construido.
        if execution.get('status') in ('timeout','row_limit'): output['status']=execution['status']
        results.append({'id':case['id'],**output,'row_count':len(execution.get('rows',[])) if execution.get('status')=='ok' else None})
    write_jsonl(args.output,results)
