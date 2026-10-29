"""Historique sur 24 h : une mesure par minute (moyenne des charges, maximum des températures),
gardée dans %LOCALAPPDATA%\\G19Monitor\\history.json pour survivre aux redémarrages."""
import time

from . import config

FILE = "history.json"
KEEP = 24 * 3600
STEP = 60          # une mesure par minute
SAVE_EVERY = 300

# clé → (libellé, unité, agrégat sur la minute : "mean" ou "max")
METRICS = {"cpu": ("CPU", "%", "mean"), "gpu": ("GPU", "%", "mean"),
           "cpu_t": ("CPU", "°C", "max"), "gpu_t": ("GPU", "°C", "max")}


class History:
    def __init__(self):
        data = config.load(FILE, {}) or {}
        cutoff = time.time() - KEEP
        self.points = [p for p in data.get("points", []) if p.get("t", 0) >= cutoff]
        self._acc = {}
        self._minute = None
        self._saved = time.time()

    def add(self, stats, sensors, now):
        values = {"cpu": stats.cpu, "gpu": (sensors or {}).get("load", stats.gpu),
                  "cpu_t": (sensors or {}).get("cpu_temp"), "gpu_t": (sensors or {}).get("temp")}
        minute = int(now // STEP)
        if self._minute is not None and minute != self._minute:
            self._flush(self._minute * STEP)
        self._minute = minute
        for k, v in values.items():
            if v is not None:
                self._acc.setdefault(k, []).append(float(v))
        if now - self._saved >= SAVE_EVERY:
            self.save()

    def _flush(self, t):
        p = {"t": t}
        for k, vals in self._acc.items():
            if vals:
                agg = METRICS[k][2]
                p[k] = round(max(vals) if agg == "max" else sum(vals) / len(vals), 1)
        self._acc = {}
        if len(p) > 1:
            self.points.append(p)
        cutoff = time.time() - KEEP
        while self.points and self.points[0]["t"] < cutoff:
            self.points.pop(0)

    def save(self):
        self._saved = time.time()
        try:
            config.save(FILE, {"points": self.points})
        except OSError:
            pass

    def series(self, key, buckets, now=None):
        """`buckets` valeurs sur les dernières 24 h (None sans mesure), agrégées comme la
        mesure (moyenne ou maximum)."""
        now = now or time.time()
        start = now - KEEP
        width = KEEP / buckets
        out = [[] for _ in range(buckets)]
        for p in self.points:
            v = p.get(key)
            if v is None or p["t"] < start:
                continue
            out[min(buckets - 1, int((p["t"] - start) / width))].append(v)
        agg = METRICS[key][2]
        return [None if not b else (max(b) if agg == "max" else sum(b) / len(b)) for b in out]

    def peak(self, key):
        """(valeur max, heure) sur 24 h, ou None."""
        best = None
        for p in self.points:
            v = p.get(key)
            if v is not None and (best is None or v > best[0]):
                best = (v, p["t"])
        return best

    def mean(self, key):
        vals = [p[key] for p in self.points if p.get(key) is not None]
        return sum(vals) / len(vals) if vals else None
