"""Ejecutor SQLite aislado por proceso, de solo lectura y con límites."""
from __future__ import annotations

import base64
import multiprocessing as mp
import re
import sqlite3
import time
from pathlib import Path

FUNCTIONS = frozenset('abs avg cast ceil ceiling char coalesce concat concat_ws count date datetime floor format glob group_concat hex ifnull iif instr julianday length like likelihood likely ln log log10 log2 lower ltrim max min mod nullif octet_length pow power printf quote replace round rtrim sign sqrt strftime substr substring sum time total trim trunc typeof unicode unixepoch unlikely upper json json_array json_array_length json_extract json_object json_quote json_type json_valid row_number rank dense_rank percent_rank cume_dist ntile lag lead first_value last_value nth_value'.split())
FUNCTIONS = FUNCTIONS | {'current_timestamp', 'current_date', 'current_time'}
REFERENCE_CLOCK = '2026-10-26 00:00:00'


def tokens(sql):
    """SQL tokens excluding comments/literals; quoted identifiers remain opaque."""
    return re.findall(r"--[^\n]*|/\*[\s\S]*?\*/|'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`[^`]*`|\[[^\]]*\]|[A-Za-z_][A-Za-z_0-9]*|[();]", sql)


def meaningful(sql):
    return [t for t in tokens(sql) if not t.startswith(('--', '/*'))]


def ordered_query(sql):
    depth = 0
    previous = ''
    for token in meaningful(sql):
        if token == '(':
            depth += 1
        elif token == ')':
            depth -= 1
        elif depth == 0:
            if previous == 'ORDER' and token.upper() == 'BY':
                return True
            previous = token.upper()
    return False


def permitted_shape(sql):
    if not isinstance(sql, str) or len(sql) > 100_000:
        return False
    ts = meaningful(sql)
    if not ts or ts[0].upper() not in {'SELECT', 'WITH'}:
        return False
    return ';' not in ts[:-1]


def authorizer(action, arg1, arg2, database, trigger):
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_RECURSIVE):
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION and (arg2 or '').lower() in FUNCTIONS:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def cell(value):
    if isinstance(value, bytes):
        return {'blob_base64': base64.b64encode(value).decode('ascii')}
    return value


def _worker(connection, path, sql, timeout, max_rows):
    start = time.monotonic()
    db = None
    try:
        db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
        db.execute('PRAGMA query_only = ON')
        db.execute('PRAGMA trusted_schema = OFF')
        db.create_function('current_timestamp', 0, lambda: REFERENCE_CLOCK, deterministic=True)
        db.create_function('current_date', 0, lambda: REFERENCE_CLOCK[:10], deterministic=True)
        db.create_function('current_time', 0, lambda: REFERENCE_CLOCK[11:], deterministic=True)
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 2_000_000)
        db.set_authorizer(authorizer)
        db.set_progress_handler(lambda: int(time.monotonic() - start > timeout), 1000)
        cursor = db.execute(sql)
        columns = [col[0] for col in cursor.description or []]
        rows = []
        byte_count = 0
        for row in cursor:
            byte_count += sum(len(str(value)) for value in row)
            if len(rows) >= max_rows or byte_count > 8_000_000:
                connection.send({'status': 'row_limit', 'columns': columns, 'rows': [], 'error': 'Resultado excede límites de filas o bytes'})
                return
            rows.append([cell(value) for value in row])
        connection.send({'status': 'ok', 'columns': columns, 'rows': rows, 'error': None})
    except sqlite3.Error as exc:
        message = str(exc)
        status = 'timeout' if 'interrupted' in message else 'rejected' if 'authorized' in message else 'error'
        connection.send({'status': status, 'columns': [], 'rows': [], 'error': message})
    except Exception as exc:
        connection.send({'status': 'error', 'columns': [], 'rows': [], 'error': str(exc)})
    finally:
        if db is not None:
            db.close()
        connection.close()


def execute(db_path, sql, timeout=5.0, max_rows=10000):
    if timeout <= 0 or max_rows < 1:
        raise ValueError('timeout y max_rows deben ser positivos')
    start = time.monotonic()
    result = {'status': 'rejected', 'columns': [], 'rows': [], 'error': 'Solo SELECT/WITH y una sentencia'}
    if permitted_shape(sql):
        if not Path(db_path).is_file():
            result.update(status='error', error=f'Base ausente: {db_path}')
        else:
            context = mp.get_context('spawn')
            reader, writer = context.Pipe(duplex=False)
            process = context.Process(target=_worker, args=(writer, str(db_path), sql, timeout, max_rows))
            process.start()
            writer.close()
            try:
                if reader.poll(timeout + 5):
                    try:
                        result = reader.recv()
                    except EOFError:
                        result.update(status='error', error='Proceso SQLite terminó sin respuesta')
                else:
                    result.update(status='timeout', error='Tiempo máximo de proceso excedido')
            finally:
                reader.close()
                process.join(.2)
                if process.is_alive():
                    process.terminate()
                    process.join()
    result['elapsed_ms'] = round((time.monotonic() - start) * 1000, 3)
    return result
