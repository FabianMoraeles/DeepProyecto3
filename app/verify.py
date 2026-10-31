import csv
import io
import json
import math
import re


def parse_response(text, structured=True):
    text = text.strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json|sql)?\s*|\s*```$', '', text, flags=re.I)
    if not structured:
        return {'status': 'ok', 'sql': text}
    obj = json.loads(text)
    if not isinstance(obj, dict) or obj.get('status') not in ('ok', 'clarification', 'refused'):
        raise ValueError('Respuesta estructurada inválida')
    if obj['status'] == 'ok':
        if not isinstance(obj.get('sql'), str) or not 0 < len(obj['sql']) <= 20000:
            raise ValueError('SQL ausente o demasiado largo')
    elif not isinstance(obj.get('message'), str) or not obj['message'].strip():
        raise ValueError('Falta el mensaje de aclaración')
    return obj


def chart_spec(result):
    cols, rows = result.get('columns', []), result.get('rows', [])
    if not rows or len(cols) < 2 or len(set(cols)) != len(cols):
        return None
    numeric = [i for i in range(len(cols)) if any(r[i] is not None for r in rows) and
               all(r[i] is None or isinstance(r[i], (int, float)) and math.isfinite(r[i]) for r in rows)]
    if not numeric:
        return None
    y = numeric[-1] if 0 in numeric else numeric[0]
    x = next((i for i in range(len(cols)) if i != y), None)
    if x is None:
        return None
    # No agregación implícita ni suma de promedios.
    labels = [str(r[x]) for r in rows]
    if len(set(labels)) != len(labels):
        return None
    dates = all(re.fullmatch(r'\d{4}-\d{2}(?:-\d{2})?', v) for v in labels)
    return {'type': 'line' if dates else 'bar', 'x': cols[x], 'y': cols[y]}


def explain(result):
    if result['status'] != 'ok':
        return 'No se obtuvo un resultado completo para esta consulta.'
    rows, cols = result['rows'], result['columns']
    if not rows:
        return 'La consulta no encontró registros que cumplan sus condiciones.'
    cells = '; '.join(f'{c}: {"sin dato" if v is None else str(v)[:160]}' for c, v in zip(cols[:4], rows[0][:4]))
    return f'Se obtuvieron {len(rows):,} filas. Primera fila del resultado: {cells}. Los valores corresponden a la consulta y al conjunto de datos seleccionado.'


def export_csv(columns, rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    def safe(value):
        # Evita que hojas de cálculo ejecuten fórmulas contenidas en texto.
        if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')):
            return "'"+value
        return value
    writer.writerow([safe(c) for c in columns])
    writer.writerows([[safe(v) for v in row] for row in rows])
    return ('\ufeff'+stream.getvalue()).encode('utf-8')
