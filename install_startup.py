"""Lance le moniteur G19 au démarrage de Windows (copie start_g19.pyw dans shell:startup)."""
import os
import sys
from pathlib import Path

STARTUP = Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs\Startup"
LAUNCHER = STARTUP / "G19 Monitor.pyw"
OLD_LAUNCHER = STARTUP / "g19_monitor.cmd"
SOURCE = Path(__file__).resolve().with_name("start_g19.pyw")


def is_installed():
    return LAUNCHER.exists()


def set_installed(install):
    OLD_LAUNCHER.unlink(missing_ok=True)
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
    print(f"Démarrage automatique installé : {LAUNCHER}" if install
          else "Démarrage automatique retiré")


if __name__ == "__main__":
    main()
