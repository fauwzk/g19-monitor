"""Données persistantes de l'appli (page affichée, historique des jeux, accès Discord)
dans %LOCALAPPDATA%\\G19Monitor."""
import json
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("G19_DATA_DIR",
                               Path(os.environ.get("LOCALAPPDATA", Path.home())) / "G19Monitor"))


def load(name, default=None):
    try:
        return json.loads((DATA_DIR / name).read_text("utf-8"))
    except (OSError, ValueError):
        return default


def save(name, data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / name
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, path)
