"""Version de l'appli : le commit git du dossier de l'appli (hash court et date), et si le dossier
a des modifications locales pas encore publiées. Lu une fois (l'appli se relance quand le code
change, y compris après une mise à jour)."""
import os
import subprocess
from functools import lru_cache

from . import instance


def _git(*args):
    try:
        out = subprocess.run(["git", "-C", str(instance.APP_DIR), *args], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=5,
                             env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
                             creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


@lru_cache(maxsize=1)
def info():
    """{"commit": "41f089a", "date": "29/10/2026", "dirty": bool} ; commit vide hors git."""
    line = _git("log", "-1", "--format=%h|%cd", "--date=format:%d/%m/%Y")
    if not line:
        return {"commit": "", "date": "", "dirty": False}
    commit, _, date = line.partition("|")
    dirty = bool(_git("status", "--porcelain", "--untracked-files=no"))
    return {"commit": commit, "date": date, "dirty": dirty}


def label(short=False):
    """« 41f089a · 29/10/2026 » (+ « · modifié » avec des modifications locales) ;
    `short` : sans l'année. « copie locale » hors git."""
    v = info()
    if not v["commit"]:
        return "copie locale"
    date = v["date"][:5] if short else v["date"]
    return f"{v['commit']} · {date}" + (" · modifié" if v["dirty"] else "")
