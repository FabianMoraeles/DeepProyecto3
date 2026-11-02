"""Carga concurrente del predictor real, sin endpoints HTTP supuestos."""
import argparse
import importlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datoclaro.data import load_split, public_request
from datoclaro.metrics import percentile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--predictor', required=True, help='app.pipeline:predict')
    parser.add_argument('--concurrency', type=int, default=20)
    parser.add_argument('--requests', type=int, default=20)
    args = parser.parse_args()
    if args.concurrency < 1 or args.requests < 1:
        parser.error('concurrency y requests deben ser positivos')
    module, name = args.predictor.split(':')
    function = getattr(importlib.import_module(module), name)
    requests = [public_request(r) for r in load_split('dev')]
    def one(index):
        start = time.monotonic()
        try:
            output = function(requests[index % len(requests)])
            return {'status': output.get('status', 'ok'), 'latency_ms': (time.monotonic()-start)*1000}
        except Exception as exc:
            return {'status': 'error', 'error': str(exc), 'latency_ms': (time.monotonic()-start)*1000}
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(one, range(args.requests)))
    times = [r['latency_ms'] for r in results]
    print(json.dumps({'n': len(results), 'ok': sum(r['status']=='ok' for r in results), 'p50_ms': percentile(times, .5), 'p95_ms': percentile(times, .95), 'results': results}, indent=2))


if __name__ == '__main__':
    main()
