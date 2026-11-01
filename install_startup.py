"""Démarrage avec Windows : met le gardien dans shell:startup (copie de start_guard.pyw).

Au démarrage, le gardien lance l'appli de chaque clavier branché (G19 Monitor pour le G19,
G15 Monitor pour un G15 / G510 / G13), puis réagit aux branchements et relance une appli qui
plante. Une seule entrée pour les deux applis : les anciennes (une par appli) sont retirées.

    python install_startup.py [--uninstall]"""
import os
import sys
from pathlib import Path

STARTUP = Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs\Startup"
LAUNCHER = STARTUP / "G19 Monitor (gardien).pyw"
SOURCE = Path(__file__).resolve().with_name("start_guard.pyw")
# entrées des versions précédentes : une par appli (lançaient l'appli directement)
OLD_LAUNCHERS = (STARTUP / "G19 Monitor.pyw", STARTUP / "G15 Monitor.pyw",
                 STARTUP / "g19_monitor.cmd")


def is_installed(mono=False):
    """Démarrage avec Windows actif (le gardien, ou une ancienne entrée par appli)."""
    return LAUNCHER.exists() or any(p.exists() for p in OLD_LAUNCHERS)


def set_installed(install, mono=False):
    """Commun aux deux applis : `mono` est gardé pour l'utilitaire du G15."""
    for old in OLD_LAUNCHERS:
        old.unlink(missing_ok=True)
    if not install:
        LAUNCHER.unlink(missing_ok=True)
        return
    # le lanceur copié pointe vers ce dossier, même si l'appli a été déplacée
    text = SOURCE.read_text("utf-8").replace(r'Path(r"D:\dev\g19")',
                                             f'Path(r"{SOURCE.parent}")')
    LAUNCHER.write_text(text, "utf-8")


def main():
    install = "--uninstall" not in sys.argv
    set_installed(install)
    print(f"Démarrage automatique installé (gardien) : {LAUNCHER}" if install
          else "Démarrage automatique retiré")


if __name__ == "__main__":
    main()
