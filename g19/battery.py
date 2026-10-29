"""Batterie des appareils Bluetooth (casque, manette…) telle que Windows la connaît, lue en
tâche de fond via PowerShell (propriétés PnP), et alerte quand elle passe sous LOW %."""
import json
import re
import subprocess
import threading
import time

EVERY = 60
LOW = 20
REALERT = 30 * 60

BATTERY_KEY = "{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2"
CONNECTED_KEY = "{83DA6326-97A6-4088-9453-A1923F573B29} 15"
# Chaque appareil Bluetooth a plusieurs nœuds : la batterie est sur l'un (profil mains libres),
# l'état « connecté » fiable sur le nœud principal BTHENUM\DEV_<adresse>. On regroupe par
# adresse Bluetooth.
SCRIPT = (
    "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "   # accents des noms
    f"$k='{BATTERY_KEY}'; $c='{CONNECTED_KEY}'; $a='DEVPKEY_Bluetooth_DeviceAddress'; "
    "@(Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like 'BTH*' } | ForEach-Object {"
    " $p = Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName $k,$c,$a"
    " -ErrorAction SilentlyContinue;"
    r" [pscustomobject]@{Name=$_.FriendlyName; Main=($_.InstanceId -like 'BTHENUM\DEV_*');"
    " Battery=($p | Where-Object KeyName -eq $k).Data;"
    " Connected=($p | Where-Object KeyName -eq $c).Data;"
    " Address=($p | Where-Object KeyName -eq $a).Data } })"
    " | Where-Object { $_.Address } | ConvertTo-Json -Compress")

# suffixes des profils Bluetooth : un même casque apparaît plusieurs fois
SUFFIXES = re.compile(r"\s+(Hands-Free( AG)?( Audio)?|Avrcp Transport|Stereo|A2DP SNK|"
                      r"Mains libres( AG)?)$", re.I)


class Batteries:
    def __init__(self):
        self.devices = []        # [{"name", "level", "connected"}]
        self.event = None        # (titre, texte, horodatage) pour le bandeau
        self.status = "lecture…"
        self._alerted = {}
        self._wake = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def refresh(self):
        """Relecture immédiate (un appareil vient de se connecter)."""
        self._wake.set()

    def _run(self):
        while True:
            try:
                self._read()
                self.status = ""
            except Exception as e:
                self.status = f"indisponible ({e.__class__.__name__})"
            self._wake.wait(EVERY)
            if self._wake.is_set():
                self._wake.clear()
                time.sleep(3)        # le temps que Windows publie le niveau du nouvel appareil

    def _read(self):
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", SCRIPT],
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=60,
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout.strip()
        data = json.loads(out) if out else []
        if isinstance(data, dict):
            data = [data]
        by_addr = {}
        for d in data:
            g = by_addr.setdefault(d.get("Address"), {"name": None, "level": None,
                                                      "connected": False, "alt": None})
            name = SUFFIXES.sub("", (d.get("Name") or "").strip()).strip()
            if d.get("Main"):
                g["name"] = name or g["name"]
                g["connected"] = bool(d.get("Connected"))
            elif name and not g["alt"]:
                g["alt"] = name
            if d.get("Battery") is not None:
                g["level"] = max(g["level"] or 0, int(d["Battery"]))
        merged = {}
        for g in by_addr.values():
            if g["level"] is None:
                continue          # appareil sans batterie connue
            name = g["name"] or g["alt"] or "?"
            merged[name] = {"name": name, "level": g["level"], "connected": g["connected"]}
        devices = sorted(merged.values(), key=lambda d: (not d["connected"], d["name"].lower()))
        now = time.time()
        for d in devices:
            if d["connected"] and d["level"] <= LOW:
                if now - self._alerted.get(d["name"], 0) >= REALERT:
                    self._alerted[d["name"]] = now
                    self.event = (d["name"], f"batterie faible : {d['level']} %", now)
            elif d["level"] > LOW + 5:
                self._alerted.pop(d["name"], None)
        self.devices = devices
