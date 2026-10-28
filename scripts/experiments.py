"""Corridas y ablaciones acotadas, sin alternar proveedores ante fallos."""
import argparse
from dataclasses import asdict, replace
import json
import os
import math
from pathlib import Path
import sys
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datoclaro.io import ROOT, write_json, read_jsonl, write_jsonl
from datoclaro.data import load_split, public_request
from datoclaro.evaluation import evaluate
from app.config import experiment
from app.pipeline import predict

ACTIVE_CONFIG = None
SPENT = 0.0
CAP = 20.0


def configured_predict(request):
    global SPENT
    prices = json.loads(os.getenv('DATOCLARO_PRICES_JSON','{}')).get(ACTIVE_CONFIG.model)
    if ACTIVE_CONFIG.provider == 'anthropic':
        # Reserva conservadora para hasta tres llamadas, incluido formato y reparación.
        if prices is None:
            return {'status':'error','sql':'','error':'Configura tarifas para respetar el presupuesto.'}
        worst = 3*(8000*prices['input']+ACTIVE_CONFIG.max_tokens*prices['output'])/1e6
        if SPENT+worst > CAP:
            return {'status':'error','sql':'','error':'Presupuesto de la campaña agotado.'}
    output=predict(request, ACTIVE_CONFIG)
    if ACTIVE_CONFIG.provider == 'anthropic':
        # Ante costo desconocido se reserva la cota completa; no se subestima.
        SPENT += output.get('cost_usd') if output.get('cost_usd') is not None else worst
    return output


def main():
    global ACTIVE_CONFIG, CAP
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    parser=argparse.ArgumentParser()
    parser.add_argument('--configs',nargs='+',choices=['I'+str(i) for i in range(1,9)],default=['I6'])
    parser.add_argument('--limit',type=int)
    parser.add_argument('--language',choices=['en','es'],default='en')
    parser.add_argument('--retrieval',choices=['lexical','semantic'],default='lexical')
    parser.add_argument('--top-k',type=int,choices=[2,4,6],default=4)
    parser.add_argument('--examples',type=int,choices=[0,3])
    parser.add_argument('--no-repair',action='store_true')
    parser.add_argument('--budget-usd',type=float,default=20)
    args=parser.parse_args()
    if not 0 < args.budget_usd <= 20: parser.error('El presupuesto debe estar entre 0 y 20 USD.')
    CAP=args.budget_usd
    if any(c!='I8' for c in args.configs):
        prices=json.loads(os.getenv('DATOCLARO_PRICES_JSON','{}'))
        if not os.getenv('ANTHROPIC_API_KEY'): parser.error('Configura ANTHROPIC_API_KEY en .env.')
        for name in args.configs:
            cfg=experiment(name)
            if cfg.provider=='anthropic' and cfg.model not in prices:
                parser.error('Configura DATOCLARO_PRICES_JSON con tarifas oficiales para '+cfg.model)
            if cfg.provider=='anthropic':
                rate=prices[cfg.model]
                if any(not isinstance(rate.get(k),(int,float)) or not math.isfinite(rate[k]) or rate[k]<0 for k in ('input','output')):
                    parser.error('Las tarifas deben ser números finitos no negativos.')
    campaign=[]
    # Register this module so the evaluator imports the same stateful adapter.
    sys.modules['datoclaro_experiment_session']=sys.modules[__name__]
    for name in args.configs:
        ACTIVE_CONFIG=replace(experiment(name),retrieval=args.retrieval,top_k=args.top_k)
        if args.examples is not None: ACTIVE_CONFIG=replace(ACTIVE_CONFIG,examples=args.examples)
        if args.no_repair: ACTIVE_CONFIG=replace(ACTIVE_CONFIG,repair=False)
        path=evaluate('dev',predictor='datoclaro_experiment_session:configured_predict',limit=args.limit,language=args.language)
        write_json(path/'experiment.json',{'experiment':name,'config':asdict(ACTIVE_CONFIG),'campaign_spent_or_reserved_usd':SPENT})
        campaign.append({'experiment':name,'run_dir':str(path),'config':asdict(ACTIVE_CONFIG)})
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    write_json(ROOT/'artifacts/campaigns'/f'{stamp}.json',{'runs':campaign,'cap_usd':CAP,'spent_or_reserved_usd':SPENT})


if __name__=='__main__': main()
