"""Lanzador idéntico en Windows, macOS y Linux: python run.py."""
import importlib.util
import subprocess
import sys
from pathlib import Path

if __name__ == '__main__':
    if importlib.util.find_spec('streamlit') is None:
        raise SystemExit('Instala dependencias: python -m pip install -r requirements.txt')
    root = Path(__file__).resolve().parent
    raise SystemExit(subprocess.call([sys.executable,'-m','streamlit','run',str(root/'streamlit_app.py'),*sys.argv[1:]],cwd=root))
