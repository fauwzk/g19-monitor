"""Alertes de seuil (températures, mémoire, disques), avec temporisation et hystérésis pour
ne pas clignoter autour du seuil."""

SUSTAIN = 5        # s au-dessus du seuil avant de déclencher
HYSTERESIS = 5     # l'alerte tombe quand la valeur repasse sous seuil - 5

# clé de réglage → (libellé, unité)
RULES = {
    "gpu_hotspot": ("Hotspot GPU", "°C"),
    "gpu_temp": ("Température GPU", "°C"),
    "cpu_temp": ("Température CPU", "°C"),
    "ram": ("RAM", "%"),
    "vram": ("VRAM", "%"),
    "disk": ("Disque", "%"),
}
DEFAULT_THRESHOLDS = {"gpu_hotspot": 100, "gpu_temp": 85, "cpu_temp": 90, "ram": 92,
                      "vram": 95, "disk": 95}


def _values(c):
    """(clé, règle, libellé, valeur) de tout ce qui est surveillé."""
    s = c.gpu.s
    out = [("gpu_hotspot", "gpu_hotspot", RULES["gpu_hotspot"][0], s.get("hotspot")),
           ("gpu_temp", "gpu_temp", RULES["gpu_temp"][0], s.get("temp")),
           ("cpu_temp", "cpu_temp", RULES["cpu_temp"][0], s.get("cpu_temp")),
           ("ram", "ram", "RAM", c.stats.ram.percent)]
    total = c.stats.vram_total
    if total and s.get("vram_mb") is not None:
        out.append(("vram", "vram", "VRAM", s["vram_mb"] * 2**20 / total * 100))
    for mount, pct in c.stats.disks:
        out.append((f"disk:{mount}", "disk", f"Disque {mount}", pct))
    return out


class AlertMonitor:
    def __init__(self):
        self.active = {}       # clé → {label, value, unit, threshold}
        self.newest = None     # dernière alerte déclenchée
        self.last_new = 0.0
        self._over = {}

    def update(self, c, now):
        cfg = c.settings
        if not cfg["alerts_on"]:
            self.active.clear()
            return
        thresholds = {**DEFAULT_THRESHOLDS, **cfg["alerts"]}
        for key, rule, label, value in _values(c):
            th = thresholds.get(rule)
            if value is None or not th:
                self._over.pop(key, None)
                self.active.pop(key, None)
                continue
            unit = RULES[rule][1]
            if value >= th:
                first = self._over.setdefault(key, now)
                if key in self.active:
                    self.active[key]["value"] = value
                elif now - first >= SUSTAIN:
                    self.active[key] = {"label": label, "value": value, "unit": unit,
                                        "threshold": th}
                    self.newest, self.last_new = key, now
            elif value < th - HYSTERESIS:
                self._over.pop(key, None)
                self.active.pop(key, None)

    def describe(self, key):
        a = self.active.get(key)
        if not a:
            return None
        return f"{a['label']} {a['value']:.0f}{a['unit']}", f"seuil {a['threshold']:.0f}{a['unit']}"
