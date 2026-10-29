"""Agrège les capteurs GPU/CPU : MSI Afterburner, puis LibreHardwareMonitor pour compléter,
et RTSS pour les FPS."""
from collections import deque

from . import afterburner, rtss
from .lhm import LhmClient

AB_MAP = {
    "GPU temperature": "temp",
    "GPU temperature 2": "hotspot",
    "Memory temperature": "mem_temp",
    "GPU usage": "load",
    "Memory usage": "vram_mb",
    "Core clock": "core_clock",
    "Memory clock": "mem_clock",
    "Power": "power",
    "Fan speed": "fan_pct",
    "Fan tachometer": "fan_rpm",
    "Core voltage": "voltage",
    "Framerate": "fps",
    "Frametime": "frametime",
    "CPU temperature": "cpu_temp",
    "CPU clock": "cpu_clock",
    "CPU power": "cpu_power",
}


class GpuMonitor:
    FPS_HISTORY = 160  # ~20 s à 8 i/s
    FT_HISTORY = 180   # temps d'image : 3 à 12 s selon la fluidité du G19

    def __init__(self):
        self.lhm = LhmClient()
        self.s = {}
        self.sources = []
        self.game = None
        self.fps_hist = deque(maxlen=self.FPS_HISTORY)
        self.ft_hist = deque(maxlen=self.FT_HISTORY)   # temps d'image (ms), un par image du G19
        self.load_hist = deque([0.0] * 60, maxlen=60)
        self.temp_max = 0.0

    def sample(self, fallback=None):
        """Toutes les secondes. `fallback` = SystemStats pour la charge/VRAM via PDH."""
        s, sources = {}, []
        ab = afterburner.read_sensors()
        if ab:
            sources.append("Afterburner")
            for name, (value, _units, _gpu) in ab.items():
                key = AB_MAP.get(name)
                if key:
                    s[key] = value
        if self.lhm.sensors:
            sources.append("LHM")
            for k, v in self.lhm.sensors.items():
                s.setdefault(k, v)
        if fallback:
            s.setdefault("load", fallback.gpu)
            s.setdefault("vram_mb", fallback.vram_used / 2**20)
            s.setdefault("cpu_load", fallback.cpu)
        self.s, self.sources = s, sources
        self.load_hist.append(s.get("load", 0.0))
        self.temp_max = max(self.temp_max, s.get("hotspot", s.get("temp", 0.0)))

    def sample_fps(self):
        """À chaque image : FPS du jeu au premier plan."""
        game = rtss.current_game()
        if game and game["fps"] > 0:
            if not self.game or self.game["pid"] != game["pid"]:
                self.fps_hist.clear()
                self.ft_hist.clear()
            self.fps_hist.append(game["fps"])
        self.game = game if game and game["fps"] > 0 else None
        return self.game

    def sample_frametime(self):
        """À chaque image du G19 : temps de la dernière image du jeu, pour le graphe."""
        if not self.game:
            return
        try:
            r = rtss.frametime(self.game)
        except OSError:
            r = None
        if r:
            self.ft_hist.append(r)

    def ft_stats(self):
        """Médiane et nombre de saccades (images > 2× la médiane et > 8 ms de plus)."""
        if len(self.ft_hist) < 10:
            return None
        vals = sorted(self.ft_hist)
        med = vals[len(vals) // 2]
        spikes = sum(1 for v in self.ft_hist if v > 2 * med and v - med > 8)
        return {"median": med, "max": vals[-1], "spikes": spikes}

    def fps_stats(self):
        if not self.fps_hist:
            return None
        vals = sorted(self.fps_hist)
        low = vals[: max(1, len(vals) // 100)]
        return {"min": vals[0], "avg": sum(vals) / len(vals), "max": vals[-1],
                "low1": sum(low) / len(low)}
