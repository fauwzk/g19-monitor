"""Capteurs LibreHardwareMonitor via son serveur web (Options → Remote Web Server → Run)."""
import json
import os
import re
import threading
import time
import urllib.request

URL = os.environ.get("G19_LHM_URL", "http://localhost:8085/data.json")

# (type de matériel, groupe LHM, motif du nom) → clé normalisée ; le premier trouvé gagne
GPU_MAP = [
    ("temp", "Temperatures", r"^GPU Core$"),
    ("hotspot", "Temperatures", r"Hot ?Spot"),
    ("mem_temp", "Temperatures", r"^GPU Memory$"),
    ("load", "Load", r"^GPU Core$"),
    ("core_clock", "Clocks", r"^GPU Core$"),
    ("mem_clock", "Clocks", r"^GPU Memory$"),
    ("power", "Powers", r"GPU Package|GPU Power|^GPU Core$"),
    ("fan_rpm", "Fans", r"."),
    ("fan_pct", "Controls", r"."),
    ("vram_mb", "SmallData", r"GPU Memory Used|D3D Dedicated Memory Used"),
    ("voltage", "Voltages", r"^GPU Core$"),
]
CPU_MAP = [
    ("cpu_temp", "Temperatures", r"Tctl|Tdie|^CPU Package$|^Core \(Tctl"),
    ("cpu_power", "Powers", r"^Package$|^CPU Package$"),
    ("cpu_load", "Load", r"^CPU Total$"),
]


def _num(text):
    m = re.match(r"\s*(-?[\d.,]+)", text or "")
    return float(m.group(1).replace(",", ".")) if m else None


def _kind(node):
    sid = node.get("SensorId") or ""
    img = node.get("ImageURL") or ""
    for child in node.get("Children", []):
        for leaf in child.get("Children", []):
            sid = sid or leaf.get("SensorId", "")
            break
    if "/gpu" in sid or any(k in img for k in ("ati", "nvidia", "amd.png", "intel-gpu")):
        return "gpu"
    if "cpu" in sid or "cpu" in img:
        return "cpu"
    return None


def parse(tree):
    out = {}
    clocks = []
    stack = [tree]
    hardware = []
    while stack:  # les nœuds matériels sont ceux dont les enfants sont des groupes de capteurs
        node = stack.pop()
        kids = node.get("Children", [])
        if kids and any(k.get("Text") in ("Temperatures", "Load", "Clocks") for k in kids):
            hardware.append(node)
        else:
            stack.extend(kids)
    for hw in hardware:
        kind = _kind(hw)
        table = GPU_MAP if kind == "gpu" else CPU_MAP if kind == "cpu" else None
        if not table:
            continue
        groups = {g.get("Text"): g.get("Children", []) for g in hw.get("Children", [])}
        for key, group, pattern in table:
            if key in out:
                continue
            for leaf in groups.get(group, []):
                if re.search(pattern, leaf.get("Text", "")):
                    v = _num(leaf.get("Value"))
                    if v is not None:
                        out[key] = v
                        break
        if kind == "cpu":
            clocks += [_num(l.get("Value")) or 0 for l in groups.get("Clocks", [])
                       if l.get("Text", "").startswith("Core")]
    if clocks:
        out["cpu_clock"] = max(clocks)
    return out


class LhmClient:
    """Interroge LHM en tâche de fond pour ne jamais bloquer l'affichage."""

    def __init__(self, url=URL):
        self.url = url
        self.sensors = {}
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            try:
                with urllib.request.urlopen(self.url, timeout=2) as r:
                    self.sensors = parse(json.loads(r.read()))
                time.sleep(1)
            except Exception:
                self.sensors = {}
                time.sleep(10)


if __name__ == "__main__":
    with urllib.request.urlopen(URL, timeout=2) as r:
        print(parse(json.loads(r.read())))
