"""Copias verificadas en almacenamiento temporal para consultas interactivas.

Evita que la latencia de carpetas sincronizadas consuma el timeout de SQLite.
La preparación se hace antes del ejecutor y nunca altera los archivos fuente.
"""
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from datoclaro.data import db_path as source_path
from datoclaro.io import ROOT, digest


@lru_cache(maxsize=11)
def db_path(db_id):
    source=source_path(db_id)
    manifest=json.loads((ROOT/'data/source_manifest.json').read_text(encoding='utf-8'))
    expected=manifest['database_files'][db_id]
    project=hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]
    directory=Path(tempfile.gettempdir())/('datoclaro-'+project)
    directory.mkdir(parents=True,exist_ok=True)
    target=directory/(db_id+'-'+expected[:16]+'.sqlite')
    if target.is_file() and digest(target)==expected:
        return target
    handle=tempfile.NamedTemporaryFile(dir=directory,suffix='.sqlite',delete=False)
    temporary=Path(handle.name)
    handle.close()
    try:
        # Copia por bloques: evita fast-copy específico del SO en carpetas sincronizadas.
        with source.open('rb') as incoming, temporary.open('wb') as outgoing:
            shutil.copyfileobj(incoming,outgoing,length=1024*1024)
        if digest(temporary)!=expected:
            raise ValueError('La base no coincide con su manifiesto; ejecuta check-data.')
        os.replace(temporary,target)
    finally:
        temporary.unlink(missing_ok=True)
    return target
