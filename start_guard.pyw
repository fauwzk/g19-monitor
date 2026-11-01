"""Lanceur sans console du gardien, mis dans shell:startup par install_startup.py : au
démarrage de Windows, il lance l'appli de chaque clavier branché (G19 Monitor, G15 Monitor),
puis réagit aux branchements et relance une appli qui plante.

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
sys.argv = [str(app / "g19" / "guard.py"), "--boot"]
runpy.run_module("g19.guard", run_name="__main__", alter_sys=True)
