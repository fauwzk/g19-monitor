"""Mises à jour par le réseau : le dossier de l'appli est un clone git du dépôt GitHub. Toutes
les CHECK_EVERY secondes, on regarde s'il y a du nouveau sur la branche suivie ; si le dossier
n'a pas de modifications locales, on l'avance (après avoir installé les nouvelles bibliothèques
s'il y en a) et l'appli se relance d'elle-même (relance sur changement du code). Avec des
modifications locales (on édite sur ce PC), rien n'est écrasé : un bandeau prévient."""
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from . import settings

CHECK_EVERY = 15 * 60
FIRST_CHECK = 90            # après le démarrage, le temps que le reste soit lancé
NOTE_MAX_AGE = 15 * 60      # bandeau « mis à jour » montré par l'instance relancée

# jamais de fenêtre de connexion ni de question dans un terminal : en arrière-plan
GIT_ENV = {"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}


class Updater:
    def __init__(self, app_dir, enabled=lambda: True):
        self.dir = Path(app_dir)
        self.enabled = enabled
        self.status = "pas encore vérifié"
        self.available = None    # (nombre de changements, résumé du dernier) quand bloqué
        self.event = None        # (titre, texte, horodatage) pour le bandeau
        self._notified = None    # dernier commit distant déjà signalé
        self._wake = threading.Event()
        self._note_from_last_run()
        threading.Thread(target=self._run, daemon=True, name="updater").start()

    def check_now(self):
        self._wake.set()

    def _note_from_last_run(self):
        """L'instance d'avant a fait la mise à jour puis s'est relancée : on le dit ici."""
        note = settings.load_state().get("update_note")
        if note and time.time() - note.get("at", 0) < NOTE_MAX_AGE:
            self.event = ("G19 Monitor mis à jour", note.get("text", ""), time.time())
        if note:
            settings.save_state(update_note=None)

    def _git(self, *args, timeout=30):
        try:
            out = subprocess.run(["git", "-C", str(self.dir), *args], capture_output=True,
                                 text=True, encoding="utf-8", errors="replace",
                                 timeout=timeout, env={**os.environ, **GIT_ENV},
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        except (OSError, subprocess.SubprocessError) as e:
            return 1, str(e)
        return out.returncode, (out.stdout or out.stderr).strip()

    def _run(self):
        self._wake.wait(FIRST_CHECK)
        while True:
            manual = self._wake.is_set()
            self._wake.clear()
            if manual or self.enabled():
                try:
                    self._check(manual)
                except Exception as e:      # réseau coupé, git absent… on réessaiera
                    self.status = f"erreur : {e.__class__.__name__}"
                # l'utilitaire affiche le résultat de la dernière vérification
                try:
                    settings.save_state(update_status={"text": self.status, "at": time.time()})
                except Exception:
                    pass
            self._wake.wait(CHECK_EVERY)

    def _check(self, manual=False):
        if not (self.dir / ".git").exists():
            self.status = "installé sans git : pas de mise à jour automatique"
            return
        code, upstream = self._git("rev-parse", "--abbrev-ref", "@{u}")
        if code:
            self.status = "aucune branche distante suivie"
            return
        code, out = self._git("fetch", "--quiet", timeout=90)
        if code:
            self.status = "GitHub injoignable" + (f" ({out[:60]})" if out else "")
            return
        behind = int(self._git("rev-list", "--count", "HEAD..@{u}")[1] or 0)
        ahead = int(self._git("rev-list", "--count", "@{u}..HEAD")[1] or 0)
        self.status = f"à jour ({time.strftime('%H:%M')})"
        if not behind:
            self.available = None
            if manual:
                self.event = ("G19 Monitor est à jour", "aucune nouvelle version sur GitHub",
                              time.time())
            return
        remote = self._git("rev-parse", "@{u}")[1]
        subject = self._git("log", "-1", "--format=%s", "@{u}")[1]
        n = f"{behind} changement{'s' if behind > 1 else ''}"
        dirty = bool(self._git("status", "--porcelain", "--untracked-files=no")[1])
        if dirty or ahead:
            # on édite sur ce PC : ne rien écraser, juste prévenir (une fois par version)
            self.available = (behind, subject)
            self.status = f"mise à jour disponible ({n}), modifications locales"
            if remote != self._notified or manual:
                self._notified = remote
                why = "modifications locales" if dirty else "commits pas encore envoyés"
                self.event = ("Mise à jour disponible", f"{n} · {why} : à faire à la main",
                              time.time())
            return
        changed = self._git("diff", "--name-only", "HEAD", "@{u}")[1].splitlines()
        if "requirements.txt" in changed and not self._install_requirements():
            return
        old = self._git("rev-parse", "--short", "HEAD")[1]
        code, out = self._git("merge", "--ff-only", "--quiet", "@{u}")
        if code:
            self.status = f"échec de la mise à jour ({out[:60]})"
            return
        self.available = None
        self.status = f"mis à jour ({old} → {remote[:7]})"
        # l'appli se relance sur le changement du code ; la nouvelle instance affichera ceci
        settings.save_state(update_note={"text": f"{n} · {subject}", "at": time.time()})
        if not any(f.endswith(".py") for f in changed):
            self.event = ("G19 Monitor mis à jour", f"{n} · {subject}", time.time())

    def _install_requirements(self):
        """Nouvelles bibliothèques : installées avant d'avancer le code qui en a besoin."""
        code, text = self._git("show", "@{u}:requirements.txt")
        if code:
            return True
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as f:
            f.write(text)
        try:
            out = subprocess.run([sys.executable.replace("pythonw.exe", "python.exe"), "-m",
                                  "pip", "install", "--user", "--quiet",
                                  "--disable-pip-version-check", "-r", f.name],
                                 capture_output=True, text=True, timeout=900,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        except (OSError, subprocess.SubprocessError) as e:
            self.status = f"échec de pip ({e.__class__.__name__})"
            return False
        finally:
            os.unlink(f.name)
        if out.returncode:
            self.status = "échec de pip : " + (out.stderr.strip().splitlines() or ["?"])[-1][:60]
            return False
        return True
