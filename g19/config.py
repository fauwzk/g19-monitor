"""Données persistantes de l'appli (page affichée, historique des jeux, accès Discord)
dans %LOCALAPPDATA%\\G19Monitor."""
import json
import os
import threading
import time
from pathlib import Path

DATA_DIR = Path(os.environ.get("G19_DATA_DIR",
                               Path(os.environ.get("LOCALAPPDATA", Path.home())) / "G19Monitor"))


def load(name, default=None):
    try:
        return json.loads((DATA_DIR / name).read_text("utf-8"))
    except (OSError, ValueError):
        return default


def save(name, data):
    """Écriture atomique. Fichier temporaire propre à chaque processus et fil (l'appli et
    l'utilitaire, ou deux fils, peuvent écrire en même temps) ; le remplacement est retenté
    un court instant quand Windows refuse parce que le fichier est ouvert ailleurs (lecture
    par l'autre processus, antivirus)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / name
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    for attempt in range(10):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 9:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.05)
