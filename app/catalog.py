from functools import lru_cache
from datoclaro.io import ROOT, read_jsonl

LABELS = {
    'california_schools': ('Educación', 'Escuelas, matrícula y resultados académicos de California', 'school'),
    'student_club': ('Vida universitaria', 'Eventos, participación y presupuesto de asociaciones', 'groups'),
    'financial': ('Finanzas', 'Cuentas, transacciones y préstamos', 'account_balance'),
    'formula_1': ('Fórmula 1', 'Circuitos, pilotos y resultados de carreras', 'sports_motorsports'),
    'european_football_2': ('Fútbol europeo', 'Equipos, jugadores y partidos', 'sports_soccer'),
    'card_games': ('Juegos de cartas', 'Cartas, colecciones y atributos', 'style'),
    'superhero': ('Superhéroes', 'Personajes, poderes y editoriales', 'bolt'),
    'toxicology': ('Toxicología', 'Moléculas, átomos y enlaces', 'science'),
    'thrombosis_prediction': ('Investigación clínica', 'Registros del benchmark; no ofrece diagnóstico', 'biotech'),
    'debit_card_specializing': ('Consumo y pagos', 'Transacciones y comercios', 'credit_card'),
    'codebase_community': ('Comunidad de código', 'Preguntas, publicaciones y contribuciones', 'code'),
}


@lru_cache(maxsize=1)
def catalog():
    return {r['db_id']: r for r in read_jsonl(ROOT / 'data/schemas.jsonl')}


# Consultas editoriales independientes del benchmark. Nunca se usan en evaluación.
DEMOS = [
    {'db_id': 'california_schools', 'question': '¿Qué condados tienen más escuelas?',
     'title': 'Escuelas por condado', 'sql': 'SELECT County AS Condado, COUNT(*) AS Escuelas FROM schools GROUP BY County ORDER BY Escuelas DESC LIMIT 10'},
    {'db_id': 'california_schools', 'question': '¿Cómo se distribuye la matrícula entre los condados?',
     'title': 'Matrícula por condado', 'sql': 'SELECT "County Name" AS Condado, SUM("Enrollment (K-12)") AS Matrícula FROM frpm GROUP BY "County Name" ORDER BY Matrícula DESC LIMIT 10'},
    {'db_id': 'california_schools', 'question': '¿Qué escuelas tienen el promedio SAT de matemáticas más alto?',
     'title': 'Resultados de matemáticas', 'sql': 'SELECT sname AS Escuela, AvgScrMath AS "Promedio SAT" FROM satscores WHERE AvgScrMath > 0 AND sname IS NOT NULL ORDER BY AvgScrMath DESC, sname LIMIT 10'},
    {'db_id': 'student_club', 'question': '¿Qué eventos tienen más asistentes?',
     'title': 'Participación en eventos', 'sql': 'SELECT e.event_name AS Evento, COUNT(*) AS Asistentes FROM attendance a JOIN event e ON a.link_to_event=e.event_id GROUP BY e.event_id, e.event_name ORDER BY Asistentes DESC LIMIT 10'},
    {'db_id': 'student_club', 'question': '¿Cómo se reparte el presupuesto por categoría?',
     'title': 'Presupuesto por categoría', 'sql': 'SELECT category AS Categoría, ROUND(SUM(amount),2) AS Presupuesto, ROUND(SUM(spent),2) AS Gastado FROM budget GROUP BY category ORDER BY Presupuesto DESC'},
    {'db_id': 'student_club', 'question': '¿Cuántos miembros hay por carrera?',
     'title': 'Miembros por carrera', 'sql': 'SELECT j.major_name AS Carrera, COUNT(*) AS Miembros FROM member m JOIN major j ON m.link_to_major=j.major_id GROUP BY j.major_id, j.major_name ORDER BY Miembros DESC LIMIT 10'},
]
