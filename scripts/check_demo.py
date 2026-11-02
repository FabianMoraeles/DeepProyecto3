"""Ejecuta las seis consultas editoriales y guarda evidencia real."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
def main():
    from app.catalog import DEMOS
    from app.pipeline import demo_predict
    from datoclaro.io import ROOT, write_json
    results=[]
    for demo in DEMOS:
        output=demo_predict(demo['db_id'],demo['question'])
        results.append({'question':demo['question'],'db_id':demo['db_id'],**output})
        print(demo['title'],output['status'],len(output.get('result',{}).get('rows',[])),flush=True)
    write_json(ROOT/'artifacts/demo_checks.json',results)
    return int(any(r['status']!='ok' for r in results))

if __name__ == '__main__': raise SystemExit(main())
