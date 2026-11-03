"""Capteurs sous Linux, à la place de gpu.GpuMonitor (Afterburner, LibreHardwareMonitor et
RTSS n'existent que sous Windows) : mêmes champs, lus dans les capteurs du noyau (psutil,
/sys/class/hwmon) et la charge GPU dans /sys/class/drm quand le pilote la publie (amdgpu).
Jeux : détectés via Steam (linux/games.py), sans FPS."""
import glob
import subprocess
import time
from collections import deque

import psutil

CPU_CHIPS = ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz")
CPU_LABELS = ("Package id 0", "Tctl", "Tdie", "")
GPU_CHIPS = ("amdgpu", "nouveau", "radeon")


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def gpu_name():
    """Nom court de la carte graphique (lspci), sinon « GPU »."""
    try:
        out = subprocess.run(["lspci", "-mm"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return "GPU"
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('" "')]
        if len(parts) > 2 and any(k in parts[0] for k in ("VGA", "3D", "Display")):
            name = parts[2]
            if "[" in name and "]" in name:          # « WhiskeyLake-U GT2 [UHD Graphics 620] »
                name = name[name.index("[") + 1:name.rindex("]")]
            for prefix in ("AMD Radeon ", "Radeon ", "NVIDIA GeForce ", "GeForce "):
                name = name.replace(prefix, "")
            return name.split("/")[0].strip() or "GPU"
    return "GPU"


def cpu_temp(temps):
    for chip in CPU_CHIPS:
        entries = temps.get(chip) or []
        for label in CPU_LABELS:
            for e in entries:
                if (e.label or "") == label and e.current:
                    return e.current
    return None


class LinuxGpu:
    FPS_HISTORY = 160
    FT_HISTORY = 180

    def __init__(self):
        self.s = {}
        self.sources = ["noyau"]
        self.game = None
        self.fps_hist = deque(maxlen=self.FPS_HISTORY)
        self.ft_hist = deque(maxlen=self.FT_HISTORY)
        self.load_hist = deque([0.0] * 60, maxlen=60)
        self.temp_max = 0.0
        # carte graphique qui publie sa charge (amdgpu : gpu_busy_percent)
        self._busy = next(iter(sorted(glob.glob("/sys/class/drm/card*/device/gpu_busy_percent"))),
                          None)
        self._vram = self._busy and self._busy.replace("gpu_busy_percent", "mem_info_vram_used")
        # Intel (i915) : pas de charge publiée ; on la déduit du temps passé en veille (RC6)
        gt = next(iter(sorted(glob.glob("/sys/class/drm/card*/gt/gt0"))), None)
        self._rc6 = gt and gt + "/rc6_residency_ms"
        self._freq = gt and gt + "/rps_act_freq_mhz"
        self._rc6_last = None

    def sample(self, fallback=None):
        s = {}
        try:
            temps = psutil.sensors_temperatures()
        except (OSError, AttributeError):
            temps = {}
        t = cpu_temp(temps)
        if t:
            s["cpu_temp"] = t
        for chip in GPU_CHIPS:
            for e in temps.get(chip) or []:
                if e.label in ("edge", "") and e.current:
                    s["temp"] = e.current
                elif e.label == "junction" and e.current:
                    s["hotspot"] = e.current
                elif e.label == "mem" and e.current:
                    s["mem_temp"] = e.current
        try:
            freq = psutil.cpu_freq()
            if freq and freq.current:
                s["cpu_clock"] = freq.current
        except (OSError, AttributeError, NotImplementedError):
            pass
        try:
            fans = psutil.sensors_fans()
        except (OSError, AttributeError):
            fans = {}
        rpm = [e.current for chip in fans.values() for e in chip if e.current]
        if rpm:
            s["fan_rpm"] = max(rpm)
        busy = _read(self._busy) if self._busy else None
        if busy and busy.isdigit():
            s["load"] = float(busy)
        vram = _read(self._vram) if self._vram else None
        if vram and vram.isdigit():
            s["vram_mb"] = int(vram) / 2**20
        if self._rc6 and "load" not in s:
            rc6, now = _read(self._rc6), time.monotonic()
            if rc6 and rc6.isdigit():
                if self._rc6_last:
                    idle = (int(rc6) - self._rc6_last[0]) / max(1.0, (now - self._rc6_last[1]) * 1000)
                    s["load"] = round(min(100.0, max(0.0, 100 * (1 - idle))), 1)
                self._rc6_last = (int(rc6), now)
        freq = _read(self._freq) if self._freq else None
        if freq and freq.isdigit():
            s["core_clock"] = float(freq)
        if fallback:
            s.setdefault("load", fallback.gpu)
            s.setdefault("vram_mb", fallback.vram_used / 2**20)
            s.setdefault("cpu_load", fallback.cpu)
        self.s = s
        self.load_hist.append(s.get("load", 0.0))
        self.temp_max = max(self.temp_max, s.get("hotspot", s.get("temp", 0.0)))

    def sample_fps(self):
        """Jeu Steam en cours (sans FPS sous Linux), pour la page GPU et les sessions."""
        from .games import current_game
        game = current_game()
        if game and (not self.game or self.game["pid"] != game["pid"]):
            self.fps_hist.clear()
        self.game = game
        return game

    def sample_frametime(self):
        pass

    def ft_stats(self):
        return None

    def fps_stats(self):
        return None
