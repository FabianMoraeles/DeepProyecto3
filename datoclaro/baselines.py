"""B0: recuperación TF-IDF de SQL de kb, filtrado por base."""
import math
import re
import time
import unicodedata
from collections import Counter


def words(text):
    text = ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))
    return re.findall(r'\w+', text)


class RetrievalBaseline:
    def __init__(self, kb):
        self.kb = kb
        counts = [Counter(words(r['question'])) for r in kb]
        df = Counter(word for count in counts for word in count)
        self.idf = {word: math.log((len(kb) + 1)/(n + 1)) + 1 for word, n in df.items()}
        self.vectors = [self.vector(count) for count in counts]

    def vector(self, count):
        v = {w: (1 + math.log(n)) * self.idf[w] for w, n in count.items() if w in self.idf}
        norm = math.sqrt(sum(x*x for x in v.values())) or 1
        return {w: x/norm for w, x in v.items()}

    def predict(self, request):
        start = time.perf_counter()
        v = self.vector(Counter(words(request['question'])))
        scores = [(sum(value * other.get(w, 0) for w, value in v.items()), row) for row, other in zip(self.kb, self.vectors) if row['db_id'] == request['db_id'] and row['id'] != request['id']]
        if not scores:
            return {'sql': '', 'status': 'refused', 'model': 'tfidf', 'cost_usd': 0, 'tokens_in': 0, 'tokens_out': 0}
        score, row = max(scores, key=lambda pair: (pair[0], pair[1]['id']))
        return {'sql': row['gold_sql'], 'status': 'ok', 'source_id': row['id'], 'similarity': score, 'model': 'tfidf', 'prompt_version': 'none', 'cost_usd': 0, 'tokens_in': 0, 'tokens_out': 0, 'latency_ms': (time.perf_counter()-start)*1000}
