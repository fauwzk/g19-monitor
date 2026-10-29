"""Conteneurs Docker : état, CPU et RAM (via la CLI `docker`), et bandeau quand un conteneur
s'arrête en erreur ou redémarre en boucle. Lu en tâche de fond ; rien si Docker est arrêté."""
import json
import shutil
import subprocess
import threading
import time

EVERY = 5               # s entre deux lectures quand Docker tourne
IDLE_EVERY = 30         # s entre deux essais quand Docker est arrêté
LOOP_RESTARTS = 3       # redémarrages en LOOP_WINDOW s = boucle
LOOP_WINDOW = 300
# codes de sortie d'un arrêt demandé (docker stop / Ctrl+C / kill) : pas une panne
STOP_CODES = {0, 130, 137, 143}

DOCKER = shutil.which("docker")


def _run(*args, timeout=15):
    try:
        out = subprocess.run([DOCKER, *args], capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=timeout,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def _pct(text):
    try:
        return float((text or "").strip().rstrip("%"))
    except ValueError:
        return 0.0


UNITS = {"b": 1, "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12,
         "kib": 2**10, "mib": 2**20, "gib": 2**30, "tib": 2**40}


def _bytes(text):
    """« 120.5MiB » → octets."""
    text = (text or "").strip().lower()
    num = text.rstrip("abcdefghijklmnopqrstuvwxyz")
    try:
        return float(num) * UNITS.get(text[len(num):].strip(), 1)
    except ValueError:
        return 0.0


class DockerMonitor:
    def __init__(self):
        self.containers = []     # [{"id", "name", "image", "state", "status", "cpu", "mem", "mem_limit", "exit", "restarts"}]
        self.status = "lecture…" if DOCKER else "Docker non installé"
        self.event = None        # (titre, texte, horodatage) pour le bandeau
        self._prev = {}          # id → (état, nombre de redémarrages)
        self._restarts = {}      # id → [horodatages des redémarrages]
        self._looping = set()
        if DOCKER:
            threading.Thread(target=self._loop, daemon=True).start()

    @property
    def running(self):
        return [c for c in self.containers if c["state"] == "running"]

    def _loop(self):
        while True:
            try:
                ok = self._read()
            except Exception as e:
                ok, self.status = False, f"erreur ({e.__class__.__name__})"
            time.sleep(EVERY if ok else IDLE_EVERY)

    def _read(self):
        out = _run("ps", "-a", "--format", "{{json .}}", timeout=10)
        if out is None:
            self.status, self.containers = "Docker arrêté", []
            self._prev.clear()
            return False
        rows = [json.loads(line) for line in out.splitlines() if line.strip()]
        ids = [r["ID"] for r in rows]
        details = {}
        if ids:
            fmt = ("{{.Id}}|{{.State.Status}}|{{.State.ExitCode}}|{{.RestartCount}}|"
                   "{{.State.OOMKilled}}")
            for line in (_run("inspect", "-f", fmt, *ids) or "").splitlines():
                try:
                    full, state, code, restarts, oom = line.split("|")
                    details[full[:12]] = (state, int(code or 0), int(restarts or 0),
                                          oom == "true")
                except ValueError:
                    continue
        stats = {}
        if any(r.get("State") == "running" for r in rows):
            for line in (_run("stats", "--no-stream", "--format", "{{json .}}", timeout=20)
                         or "").splitlines():
                try:
                    s = json.loads(line)
                except ValueError:
                    continue
                used, _, limit = (s.get("MemUsage") or "").partition("/")
                stats[s.get("ID", "")[:12]] = (_pct(s.get("CPUPerc")), _bytes(used), _bytes(limit))
        now = time.time()
        containers = []
        for r in rows:
            cid = r["ID"][:12]
            state, code, restarts, oom = details.get(cid, (r.get("State", ""), 0, 0, False))
            cpu, mem, limit = stats.get(cid, (0.0, 0.0, 0.0))
            name = (r.get("Names") or cid).split(",")[0]
            containers.append({"id": cid, "name": name, "image": r.get("Image", ""),
                               "state": state, "status": r.get("Status", ""), "cpu": cpu,
                               "mem": mem, "mem_limit": limit, "exit": code,
                               "restarts": restarts, "oom": oom})
            self._watch(cid, name, state, code, restarts, now, oom)
        order = {"restarting": 0, "running": 1, "paused": 2}
        containers.sort(key=lambda c: (order.get(c["state"], 3), -c["cpu"], c["name"]))
        self.containers = containers
        self.status = ""
        return True

    def _watch(self, cid, name, state, code, restarts, now, oom=False):
        prev = self._prev.get(cid)
        self._prev[cid] = (state, restarts)
        if prev is None:
            return                       # conteneur vu pour la première fois
        p_state, p_restarts = prev
        if restarts > p_restarts or (state == "restarting" and p_state != "restarting"):
            times = [t for t in self._restarts.get(cid, []) if now - t < LOOP_WINDOW] + [now]
            self._restarts[cid] = times
            if len(times) >= LOOP_RESTARTS and cid not in self._looping:
                self._looping.add(cid)
                self.event = (name, f"redémarre en boucle ({len(times)}× en 5 min)", now)
                return
        elif state == "running" and not self._restarts.get(cid):
            self._looping.discard(cid)
        if p_state == "running" and state in ("exited", "dead"):
            if oom:
                self.event = (name, "arrêté : mémoire insuffisante (OOM)", now)
            elif code not in STOP_CODES:
                self.event = (name, f"arrêté en erreur (code {code})", now)
        if self._restarts.get(cid) and now - self._restarts[cid][-1] > LOOP_WINDOW:
            self._restarts.pop(cid, None)
            self._looping.discard(cid)
