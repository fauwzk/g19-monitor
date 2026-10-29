"""État Git des dossiers des sessions Claude (branche, fichiers modifiés, commits à pousser),
et de la PR / CI de la branche via GitHub CLI (`gh`) s'il est installé et connecté.
Lu en tâche de fond : la page Claude ne lit que le cache."""
import json
import shutil
import subprocess
import threading
import time

GIT_EVERY = 15          # s entre deux lectures `git status` d'un dossier
GH_EVERY = 120          # s entre deux lectures de la PR (réseau)
FORGET = 600            # dossier plus demandé depuis 10 min : on arrête de le suivre

GIT = shutil.which("git")
GH = shutil.which("gh")


def _run(args, cwd, timeout=10):
    try:
        out = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=timeout,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def parse_status(out):
    """Sortie de `git status --porcelain=v2 --branch` → dict."""
    info = {"branch": "", "ahead": 0, "behind": 0, "changed": 0, "untracked": 0}
    for line in out.splitlines():
        if line.startswith("# branch.head "):
            info["branch"] = line.split(" ", 2)[2]
        elif line.startswith("# branch.ab "):
            a, b = line.split()[2:4]
            info["ahead"], info["behind"] = int(a), -int(b)
        elif line.startswith(("1 ", "2 ", "u ")):
            info["changed"] += 1
        elif line.startswith("? "):
            info["untracked"] += 1
    if info["branch"] == "(detached)":
        info["branch"] = "détachée"
    return info


def ci_state(checks):
    """statusCheckRollup de gh → "ok" / "fail" / "running" / "" (pas de CI)."""
    states = set()
    for c in checks or []:
        s = (c.get("conclusion") or c.get("state") or c.get("status") or "").upper()
        if s in ("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED"):
            states.add("fail")
        elif s in ("SUCCESS", "NEUTRAL", "SKIPPED"):
            states.add("ok")
        elif s:
            states.add("running")
    for s in ("fail", "running", "ok"):
        if s in states:
            return s
    return ""


class GitStatus:
    def __init__(self):
        self._repos = {}        # cwd → {"info", "pr", "git_at", "gh_at", "asked"}
        self._lock = threading.Lock()
        self._wake = threading.Event()
        if GIT:
            threading.Thread(target=self._run, daemon=True).start()

    def get(self, cwd):
        """État connu du dossier (None si pas un dépôt ou pas encore lu)."""
        if not cwd or not GIT:
            return None
        with self._lock:
            r = self._repos.get(cwd)
            if r is None:
                r = self._repos[cwd] = {"info": None, "pr": None, "git_at": 0, "gh_at": 0}
                self._wake.set()
            r["asked"] = time.time()
            if not r["info"]:
                return None
            return {**r["info"], "pr": r["pr"]}

    def _run(self):
        while True:
            now = time.time()
            with self._lock:
                for cwd in [c for c, r in self._repos.items() if now - r["asked"] > FORGET]:
                    del self._repos[cwd]
                todo = list(self._repos.items())
            for cwd, r in todo:
                if now - r["git_at"] >= GIT_EVERY:
                    r["git_at"] = now
                    out = _run([GIT, "status", "--porcelain=v2", "--branch"], cwd)
                    r["info"] = parse_status(out) if out is not None else None
                if GH and r["info"] and now - r["gh_at"] >= GH_EVERY:
                    r["gh_at"] = now
                    r["pr"] = self._pr(cwd)
            self._wake.wait(3)
            self._wake.clear()

    @staticmethod
    def _pr(cwd):
        out = _run([GH, "pr", "view", "--json", "number,state,isDraft,statusCheckRollup"], cwd,
                   timeout=20)
        if not out:
            return None
        try:
            data = json.loads(out)
        except ValueError:
            return None
        return {"number": data.get("number"), "state": (data.get("state") or "").lower(),
                "draft": bool(data.get("isDraft")),
                "ci": ci_state(data.get("statusCheckRollup"))}
