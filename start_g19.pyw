"""Lanceur sans console du moniteur G19, à mettre dans shell:startup (copie ou raccourci).

Si ce fichier est copié ailleurs que dans le dossier de l'appli, il utilise APP_DIR ci-dessous.
"""
import os
import runpy
import sys
from pathlib import Path

APP_DIR = Path(r"D:\dev\g19")

here = Path(__file__).resolve().parent
app = here if (here / "g19_monitor.py").exists() else APP_DIR
os.chdir(app)
sys.path.insert(0, str(app))
sys.argv = [str(app / "g19_monitor.py")]
runpy.run_path(sys.argv[0], run_name="__main__")
