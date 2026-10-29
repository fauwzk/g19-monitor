"""Lecture des états de session Claude Code écrits par claude_hook.py."""
import json
import os
import time
from pathlib import Path

import psutil

STATUS_DIR = Path(os.environ.get("G19_CLAUDE_DIR",
                                 Path.home() / ".claude" / "g19" / "sessions"))

WORKING_STALE = 15 * 60   # « travaille » sans nouvelle depuis 15 min → probablement interrompu
WAITING_STALE = 30 * 60   # question sans réponse depuis 30 min → on arrête de la signaler
IDLE_HIDE = 2 * 3600      # sessions au repos masquées après 2 h
FORGET = 12 * 3600        # fichiers supprimés après 12 h sans activité

PRIORITY = {"waiting": 0, "working": 1, "idle": 2, "stale": 3}


def claude_running():
    """Claude est-il ouvert ? Appli desktop ou Claude Code (binaire natif ou via node)."""
    for p in psutil.process_iter(["name"]):
        name = (p.info["name"] or "").lower()
        if name == "claude.exe":
            return True
        if name == "node.exe":
            try:
                if any("claude" in a.lower() for a in p.cmdline()):
                    return True
            except (psutil.Error, OSError):
                pass
    return False


class Session(dict):
    __getattr__ = dict.get


def read_sessions(now=None):
    now = now or time.time()
    out = []
    if not STATUS_DIR.is_dir():
        return out
    for path in STATUS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        age = now - data.get("updated", 0)
        if age > FORGET:
            try:
                path.unlink()
            except OSError:
                pass
            continue
        state = data.get("state", "idle")
        if state == "working" and age > WORKING_STALE:
            state = "stale"
        elif state == "waiting" and age > WAITING_STALE:
            state = "idle"
        if state in ("idle", "stale") and age > IDLE_HIDE:
            continue
        data["state"] = state
        data["age"] = age
        data["name"] = Path(data.get("cwd") or "?").name or data.get("cwd", "?")
        out.append(Session(data))
    out.sort(key=lambda s: (PRIORITY.get(s.state, 9), s.age))
    return out
