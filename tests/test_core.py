import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path

from datoclaro.data import make_splits, check_splits, normalize, public_request
from datoclaro.execution import execute, ordered_query
from datoclaro.metrics import result_equal, mcnemar, summary
from datoclaro.baselines import RetrievalBaseline


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = Path(self.directory.name) / 'with spaces.sqlite'
        with closing(sqlite3.connect(self.database)) as db:
            db.executescript('CREATE TABLE items (id INTEGER, amount REAL); INSERT INTO items VALUES (1, 3.5), (2, NULL), (3, 3.5);')

    def tearDown(self):
        self.directory.cleanup()

    def test_query(self):
        r = execute(self.database, 'SELECT sum(amount) FROM items')
        self.assertEqual(r['status'], 'ok')
        self.assertEqual(r['rows'], [[7.0]])

    def test_write_rejected(self):
        for sql in ['DELETE FROM items', 'WITH a AS (SELECT 1) DELETE FROM items', 'ATTACH DATABASE ":memory:" AS bad', 'PRAGMA writable_schema=ON', "SELECT load_extension('bad')", 'SELECT 1; DROP TABLE items;']:
            with self.subTest(sql=sql):
                self.assertNotEqual(execute(self.database, sql)['status'], 'ok')
        self.assertEqual(execute(self.database, 'SELECT count(*) FROM items')['rows'], [[3]])

    def test_limit_and_timeout(self):
        self.assertEqual(execute(self.database, 'SELECT * FROM items', max_rows=1)['status'], 'row_limit')
        recursive = 'WITH RECURSIVE a(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM a) SELECT SUM(x) FROM a'
        self.assertEqual(execute(self.database, recursive, timeout=.05)['status'], 'timeout')

    def test_literal_semicolon_and_cte(self):
        self.assertEqual(execute(self.database, "WITH a AS (SELECT ';' x) SELECT x FROM a")['rows'], [[';']])

    def test_current_time_is_reproducible(self):
        self.assertEqual(execute(self.database, 'SELECT CURRENT_TIMESTAMP, CURRENT_DATE')['rows'], [['2026-10-26 00:00:00', '2026-10-26']])


class MetricsTests(unittest.TestCase):
    def result(self, rows):
        return {'status': 'ok', 'columns': ['v'], 'rows': rows}

    def test_multiset_order_and_null(self):
        a = self.result([[1], [2], [1]])
        b = self.result([[1.0], [1], [2]])
        self.assertTrue(result_equal(a, b))
        self.assertFalse(result_equal(a, b, ordered=True))
        self.assertFalse(result_equal(a, self.result([[1], [2], [2]])))
        self.assertFalse(result_equal(self.result([[None]]), self.result([[0]])))
        self.assertTrue(result_equal(self.result([[.3]]), self.result([[.1+.2]])))

    def test_order_detection(self):
        self.assertFalse(ordered_query('SELECT * FROM (SELECT * FROM a ORDER BY x)'))
        self.assertTrue(ordered_query('SELECT * FROM a ORDER /* comment */ BY x'))
        self.assertFalse(ordered_query("SELECT 'ORDER BY' FROM a"))

    def test_missing_in_denominator(self):
        rows = [{'id': 'a', 'gold_status': 'ok', 'prediction_status': 'ok', 'correct': True}, {'id': 'b', 'gold_status': 'ok', 'prediction_status': 'missing', 'correct': False}]
        self.assertEqual(summary(rows)['execution_accuracy'], .5)
        self.assertIsNone(summary(rows)['cost_observed_total_usd'])
        self.assertEqual(mcnemar([True]*6, [False]*6)['p_value'], .03125)


class DataTests(unittest.TestCase):
    def rows(self):
        return normalize([{'question_id': i, 'db_id': 'school', 'question': f'question {i}', 'SQL': f'SELECT {i//2}', 'difficulty': 'simple'} for i in range(30)])

    def test_groups_and_reproducibility(self):
        rows = self.rows()
        s = make_splits(rows)
        check_splits(rows, s)
        self.assertEqual(s, make_splits(rows))
        self.assertTrue(all(s['splits'].values()))

    def test_predictor_never_receives_gold(self):
        request = public_request(self.rows()[0])
        self.assertEqual(set(request), {'id', 'db_id', 'question', 'language'})

    def test_baseline_same_database(self):
        model = RetrievalBaseline(self.rows()[:2])
        self.assertEqual(model.predict({'id': 'test', 'db_id': 'different', 'question': 'question'})['status'], 'refused')


if __name__ == '__main__':
    unittest.main()
