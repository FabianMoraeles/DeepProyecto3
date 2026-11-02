import json
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.config import Config, experiment
from app.pipeline import predict, demo_predict
from app.retrieval import bridge_tables, retrieve
from app.verify import parse_response, chart_spec, export_csv, explain
from datoclaro.data import load_split


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'fixture.sqlite'
        with closing(sqlite3.connect(self.path)) as conn:
            conn.executescript('CREATE TABLE items (id INTEGER, amount REAL); INSERT INTO items VALUES (1, 5), (2, 8);')
        self.request = {'id':'visitor', 'db_id':'california_schools', 'question':'Suma los importes', 'language':'es'}
        self.context = {'schema':'TABLE items (id INTEGER, amount REAL)', 'tables':['items'], 'examples':[], 'method':'fixture'}

    def tearDown(self):
        self.tmp.cleanup()

    def run_responses(self, responses, **kwargs):
        self.prompts = []
        def client(system, prompt, cfg):
            self.prompts.append(prompt)
            response = responses[len(self.prompts)-1]
            return {'text':response, 'model':'fixture-only', 'tokens_in':10, 'tokens_out':5, 'cost_usd':None}
        with patch('app.pipeline.db_path', return_value=self.path), patch('app.pipeline.retrieve', return_value=self.context):
            return predict(self.request, Config(**kwargs), client)

    def test_success_and_grounded_explanation(self):
        output = self.run_responses(['{"status":"ok","sql":"SELECT sum(amount) AS Total FROM items"}'])
        self.assertEqual(output['status'], 'ok')
        self.assertEqual(output['result']['rows'], [[13.0]])
        self.assertIn('13.0', output['explanation'])
        self.assertIsNone(output['cost_usd'])

    def test_one_repair(self):
        output = self.run_responses(['{"status":"ok","sql":"SELECT missing FROM items"}', '{"status":"ok","sql":"SELECT amount FROM items"}'])
        self.assertTrue(output['repaired'])
        self.assertEqual(output['attempts'], 2)
        self.assertEqual(output['tokens_in'], 20)

    def test_failed_repair_stops(self):
        output = self.run_responses(['{"status":"ok","sql":"SELECT missing FROM items"}']*2)
        self.assertEqual(output['status'], 'error')
        self.assertEqual(output['attempts'],2)

    def test_rejected_write_not_repaired(self):
        output = self.run_responses(['{"status":"ok","sql":"DELETE FROM items"}'])
        self.assertEqual(output['status'],'refused')
        self.assertEqual(output['attempts'],1)
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM items').fetchone()[0],2)

    def test_format_retry(self):
        output = self.run_responses(['not json','{"status":"ok","sql":"SELECT 1"}'])
        self.assertEqual(output['status'],'ok')
        self.assertEqual(output['attempts'],2)

    def test_clarification_and_no_gold(self):
        self.request.update(gold_sql='SECRET_GOLD', evidence='SECRET_EVIDENCE')
        output = self.run_responses(['{"status":"clarification","message":"¿Qué período?"}'])
        self.assertEqual(output['status'],'clarification')
        self.assertNotIn('SECRET', ''.join(self.prompts))

    def test_validation_before_provider(self):
        for req, expected in [({**self.request,'question':''},'clarification'), ({**self.request,'question':'x'*2001},'refused'),({**self.request,'db_id':'../secret'},'refused')]:
            with patch('app.pipeline.complete') as client:
                self.assertEqual(predict(req)['status'],expected)
                client.assert_not_called()

    def test_retrieval_only_kb(self):
        request = {**self.request, 'question':'¿Cuántas escuelas hay por condado?'}
        result = retrieve(request,Config())
        kb = {r['id'] for r in load_split('kb')}
        self.assertTrue({r['id'] for r in result['examples']} <= kb)
        self.assertIn('schools',result['tables'])

    def test_bridges(self):
        tables = [{'name':n,'foreign_keys':f} for n,f in [('a',[{'table':'bridge'}]),('bridge',[{'table':'b'}]),('b',[])]]
        self.assertEqual([t['name'] for t in bridge_tables({'a','b'},tables)],['a','bridge','b'])

    def test_chart_and_export(self):
        result={'status':'ok','columns':['City','Count'],'rows':[['A',4],['B',2]]}
        self.assertEqual(chart_spec(result),{'type':'bar','x':'City','y':'Count'})
        self.assertIsNone(chart_spec({**result,'rows':[['A',4],['A',2]]}))
        self.assertIn("'=HYPERLINK",export_csv(['x'],[['=HYPERLINK("bad")']]).decode())
        self.assertIn('no encontró',explain({**result,'rows':[]}))

    def test_demo_not_fallback(self):
        result=demo_predict('california_schools','Pregunta no registrada')
        self.assertEqual(result['status'],'clarification')

    def test_ablations_distinct(self):
        self.assertFalse(experiment('I1').structured)
        self.assertFalse(experiment('I4').repair)
        self.assertTrue(experiment('I5').repair)
        self.assertEqual(experiment('I8').provider,'ollama')


if __name__ == '__main__': unittest.main()
