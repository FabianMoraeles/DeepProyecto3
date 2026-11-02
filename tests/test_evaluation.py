import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from datoclaro.evaluation import evaluate
from datoclaro.io import write_jsonl


class RunnerTests(unittest.TestCase):
    def test_duplicate_predictions_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'predictions.jsonl'
            write_jsonl(path, [{'id': 'a', 'sql': 'SELECT 1'}, {'id': 'a', 'sql': 'SELECT 1'}])
            with patch('datoclaro.evaluation.load_split', return_value=[{'id': 'a', 'db_id': 'demo'}]), patch('datoclaro.evaluation.db_path', return_value=Path('demo.sqlite')):
                with self.assertRaisesRegex(ValueError, 'duplicadas'):
                    evaluate('dev', predictions=path)

    def test_unreviewed_spanish_not_evaluated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data').mkdir()
            (root / 'data/spanish_review.csv').write_text('id,question_es,translator,reviewer,reviewed\na,Hola,,,false\n')
            with patch('datoclaro.evaluation.ROOT', root), patch('datoclaro.evaluation.load_split', return_value=[{'id': 'a'}]):
                with self.assertRaisesRegex(ValueError, 'No hay casos'):
                    evaluate('dev', baseline=True, language='es')
