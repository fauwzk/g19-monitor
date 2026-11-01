"""Lance le moniteur G19 au démarrage de Windows (copie start_g19.pyw dans shell:startup).

    python install_startup.py [--uninstall] [--g15]   # --g15 : la version G15 / G510"""
import os
import sys
from pathlib import Path

STARTUP = Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs\Startup"
LAUNCHER = STARTUP / "G19 Monitor.pyw"
OLD_LAUNCHER = STARTUP / "g19_monitor.cmd"
SOURCE = Path(__file__).resolve().with_name("start_g19.pyw")
# version monochrome (G15 / G510), lancée à côté
MONO_LAUNCHER = STARTUP / "G15 Monitor.pyw"
MONO_SOURCE = SOURCE.with_name("start_g15.pyw")


def is_installed(mono=False):
    return (MONO_LAUNCHER if mono else LAUNCHER).exists()


def set_installed(install, mono=False):
    launcher, source = (MONO_LAUNCHER, MONO_SOURCE) if mono else (LAUNCHER, SOURCE)
    if not mono:
        OLD_LAUNCHER.unlink(missing_ok=True)
    if not install:
        launcher.unlink(missing_ok=True)
        return
    # le lanceur copié pointe vers ce dossier, même si l'appli a été déplacée
    text = source.read_text("utf-8").replace(r'Path(r"D:\dev\g19")',
                                             f'Path(r"{source.parent}")')
    launcher.write_text(text, "utf-8")


def main():
    install = "--uninstall" not in sys.argv
    mono = "--g15" in sys.argv
    set_installed(install, mono)
    launcher = MONO_LAUNCHER if mono else LAUNCHER
    print(f"Démarrage automatique installé : {launcher}" if install
          else "Démarrage automatique retiré")


if __name__ == "__main__":
    main()
