"""Prepara bases de demostración desde el ZIP oficial, fuera de carpetas sincronizadas."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    from datoclaro.io import ROOT, digest
    parser=argparse.ArgumentParser()
    parser.add_argument('--archive',type=Path,required=True,help='dev.zip oficial de BIRD')
    args=parser.parse_args()
    expected_archive='cdd6d19faeb45a23970b98d3ef6c40a87987c95459c2cf12076897a60cf5a630'
    if digest(args.archive)!=expected_archive:
        raise ValueError('El ZIP no coincide con el manifiesto oficial fijado.')
    manifest=json.loads((ROOT/'data/source_manifest.json').read_text(encoding='utf-8'))
    project=hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]
    destination=Path(tempfile.gettempdir())/('datoclaro-'+project)
    destination.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='datoclaro-extract-') as work:
        inner=Path(work)/'databases.zip'
        with zipfile.ZipFile(args.archive) as outer:
            with outer.open('dev_20240627/dev_databases.zip') as source, inner.open('wb') as output:
                shutil.copyfileobj(source,output,length=1024*1024)
        with zipfile.ZipFile(inner) as databases:
            for db_id in ('california_schools','student_club'):
                matches=[name for name in databases.namelist() if Path(name).parts[-2:]==(db_id,db_id+'.sqlite')]
                if len(matches)!=1: raise ValueError('Base no encontrada en ZIP: '+db_id)
                expected=manifest['database_files'][db_id]
                temporary=Path(work)/(db_id+'.sqlite')
                with databases.open(matches[0]) as source, temporary.open('wb') as output:
                    shutil.copyfileobj(source,output,length=1024*1024)
                if digest(temporary)!=expected: raise ValueError('Hash incorrecto: '+db_id)
                os.replace(temporary,destination/(db_id+'-'+expected[:16]+'.sqlite'))
                print(db_id,'preparada y verificada',flush=True)


if __name__=='__main__': main()
