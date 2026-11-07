"""Gestionnaire des tâches du G19 : les processus regroupés par nom (chrome.exe × 30 = une
ligne), avec leur CPU et leur mémoire, et la fin de tâche d'un groupe.

Le relevé tourne en tâche de fond, seulement tant que la page Processus est affichée (un
passage sur ~300 processus coûte quelques dizaines de ms)."""
import ctypes
import os
import struct
import threading
import time

import psutil

EVERY = 2.0             # s entre deux relevés pendant que la page est affichée
SORTS = ("cpu", "mem", "name")
SORT_LABELS = {"cpu": "CPU", "mem": "Mémoire", "name": "Nom"}

# jamais terminés depuis le G19 : Windows en a besoin (écran bleu, session fermée) ou ils
# ne se laissent de toute façon pas faire
PROTECTED = {"system", "system idle process", "registry", "smss.exe", "csrss.exe",
             "wininit.exe", "winlogon.exe", "services.exe", "lsass.exe", "lsaiso.exe",
             "svchost.exe", "dwm.exe", "fontdrvhost.exe", "memory compression",
             "secure system", "sihost.exe", "ctfmon.exe", "audiodg.exe", "spoolsv.exe",
             "msmpeng.exe", "searchindexer.exe", "conhost.exe", "taskhostw.exe",
             "runtimebroker.exe", "startmenuexperiencehost.exe", "shellexperiencehost.exe",
             "textinputhost.exe", "lghub.exe", "lcore.exe"}


_ntdll = ctypes.WinDLL("ntdll")
_SYSTEM_PROCESS_INFORMATION = 5
_MISMATCH = 0xC0000004 - 2**32       # STATUS_INFO_LENGTH_MISMATCH, en NTSTATUS signé
_buf = {"size": 1 << 20}


def snapshot():
    """Tous les processus en un seul appel à Windows (bien plus rapide que psutil, qui
    interroge chaque processus, lentement pour les protégés) : {pid: (nom, temps CPU en
    100 ns, mémoire privée en octets)}. Dispositions de SYSTEM_PROCESS_INFORMATION (x64)."""
    size = _buf["size"]
    while True:
        buf = ctypes.create_string_buffer(size)
        need = ctypes.c_ulong(0)
        status = _ntdll.NtQuerySystemInformation(_SYSTEM_PROCESS_INFORMATION, buf, size,
                                                 ctypes.byref(need))
        if status == _MISMATCH:
            size = max(size * 2, need.value + 65536)
            _buf["size"] = size
            continue
        if status != 0:
            raise OSError(f"NtQuerySystemInformation : {status:#x}")
        break
    raw = buf.raw
    out, off = {}, 0
    while True:
        nxt = struct.unpack_from("<I", raw, off)[0]
        private = struct.unpack_from("<q", raw, off + 8)[0]
        user, kernel = struct.unpack_from("<qq", raw, off + 40)
        length, _maxlen, _pad, addr = struct.unpack_from("<HHIQ", raw, off + 56)
        pid = struct.unpack_from("<Q", raw, off + 80)[0]
        if addr and length:
            name = ctypes.wstring_at(addr, length // 2)   # pointe dans `buf`
        else:
            name = "System Idle Process" if pid == 0 else "System"
        out[pid] = (name, user + kernel, private)
        if not nxt:
            return out
        off += nxt


def _own_tree():
    """L'appli elle-même et ses parents (python, pythonw, le gardien) : pas de suicide."""
    pids = {os.getpid()}
    try:
        for p in psutil.Process().parents():
            pids.add(p.pid)
    except psutil.Error:
        pass
    return pids


class ProcessMonitor:
    def __init__(self):
        self.groups = []            # [{"name", "count", "cpu", "mem", "pids"}], trié
        self.sort = "cpu"
        self.total_cpu = 0.0
        self.total_mem = 0.0        # Go utilisés
        self.count = 0
        self.updated_at = 0.0
        self.event = None           # (titre, texte, horodatage) après une fin de tâche
        self._prev = {}             # pid → (nom, temps CPU) du relevé précédent
        self._prev_at = 0.0
        self._shown = 0.0
        self._wake = threading.Event()
        self._lock = threading.Lock()
        self._ncpu = psutil.cpu_count() or 1
        self._own = _own_tree()
        threading.Thread(target=self._run, name="processus", daemon=True).start()

    # --- appelé par la boucle de l'écran ---

    def show(self, on):
        """Page affichée ou non : le relevé ne tourne que pendant qu'on la regarde."""
        if on:
            first = time.time() - self._shown > EVERY * 3
            self._shown = time.time()
            if first:
                self._wake.set()

    def set_sort(self, sort):
        self.sort = sort
        with self._lock:
            self.groups = self._sorted(self.groups)

    def next_sort(self):
        self.set_sort(SORTS[(SORTS.index(self.sort) + 1) % len(SORTS)])

    def protected(self, group):
        return group["name"].lower() in PROTECTED or bool(set(group["pids"]) & self._own)

    def kill(self, group):
        """Termine tous les processus du groupe (en douceur, puis de force après 3 s).
        Renvoie (réussis, refusés)."""
        if self.protected(group):
            self.event = (f"{group['name']} protégé", "nécessaire à Windows ou à l'appli",
                          time.time())
            return 0, len(group["pids"])
        procs, denied = [], 0
        for pid in group["pids"]:
            try:
                p = psutil.Process(pid)
                if p.name() != group["name"]:      # pid réutilisé entre-temps
                    continue
                p.terminate()
                procs.append(p)
            except psutil.NoSuchProcess:
                pass
            except psutil.Error:
                denied += 1
        if procs:
            threading.Thread(target=self._finish, args=(procs,), daemon=True).start()
        n = len(procs)
        if n and not denied:
            text = f"{n} processus terminé" + ("s" if n > 1 else "")
        elif n:
            text = f"{n} terminé(s), {denied} refusé(s) : droits administrateur"
        else:
            text = "refusé : droits administrateur" if denied else "déjà fermé"
        self.event = (f"Fin de tâche · {group['name']}", text, time.time())
        self._wake.set()
        return n, denied

    @staticmethod
    def _finish(procs):
        _gone, alive = psutil.wait_procs(procs, timeout=3)
        for p in alive:
            try:
                p.kill()
            except psutil.Error:
                pass

    # --- fil du relevé ---

    def _run(self):
        while True:
            self._wake.wait(EVERY)
            self._wake.clear()
            if time.time() - self._shown > EVERY * 3:
                continue                    # page pas affichée : on ne fait rien
            try:
                self._sample()
            except Exception:               # un relevé raté : le suivant
                pass

    def _sample(self):
        now = time.perf_counter()
        procs = snapshot()
        elapsed = (now - self._prev_at) if self._prev_at else 0.0
        groups = {}
        for pid, (name, cpu_time, mem) in procs.items():
            if pid == 0:
                continue                    # processus inactif du système
            prev = self._prev.get(pid)
            cpu = 0.0
            if prev and prev[0] == name and elapsed > 0:
                cpu = max(0.0, (cpu_time - prev[1]) / 1e7 / elapsed / self._ncpu * 100)
            g = groups.setdefault(name.lower(), {"name": name, "count": 0, "cpu": 0.0,
                                                 "mem": 0, "pids": []})
            g["count"] += 1
            g["cpu"] += cpu
            g["mem"] += mem
            g["pids"].append(pid)
        self._prev = {pid: (v[0], v[1]) for pid, v in procs.items()}
        self._prev_at = now
        vm = psutil.virtual_memory()
        with self._lock:
            self.groups = self._sorted(list(groups.values()))
            self.count = len(procs) - (1 if 0 in procs else 0)
            self.total_cpu = psutil.cpu_percent(None)
            self.total_mem = vm.used / 2**30
            self.updated_at = time.time()

    def _sorted(self, groups):
        if self.sort == "name":
            return sorted(groups, key=lambda g: g["name"].lower())
        key = "cpu" if self.sort == "cpu" else "mem"
        return sorted(groups, key=lambda g: (-g[key], -g["mem"], g["name"].lower()))
