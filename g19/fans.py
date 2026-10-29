"""Profils de ventilateurs de la carte mère, via le serveur web de LibreHardwareMonitor.

GCC (Gigabyte Control Center) n'est pas pilotable ; LHM règle directement les sorties PWM de la
puce de la carte mère. Hors profil « auto », les courbes de GCC/BIOS sont remplacées par une
vitesse fixe. Sécurités :
- la pompe (et tout ce qui s'appelle « pump ») n'est jamais touchée, ni le ventilo du GPU ;
- retour automatique en « auto » si le CPU ou le hotspot GPU chauffe ;
- retour en « auto » à la fermeture de l'appli ;
- vitesse minimale garantie.
"""
import json
import logging
import threading
import time
import urllib.parse
import urllib.request

from .lhm import URL as LHM_DATA

log = logging.getLogger("g19")

BASE = LHM_DATA.rsplit("/", 1)[0]
PROFILES = {"auto": None, "silent": 35, "balanced": 55, "performance": 75, "max": 100}
LABELS = {"auto": "auto (GCC)", "silent": "silencieux", "balanced": "équilibré",
          "performance": "performance", "max": "maximum"}
MIN_PCT = 30            # jamais en dessous, quel que soit le profil
SAFE_CPU = 85           # °C : au-delà, retour en auto (sauf profil maximum) — réglable
SAFE_GPU_HOTSPOT = 95
SAFE_RANGE = (60, 100)  # bornes acceptées pour ces seuils
RECOVER_MARGIN = 8      # °C sous le seuil pour considérer que c'est redescendu
RECOVER_SECONDS = 60    # pendant tout ce temps avant de reprendre le profil choisi (réglable)
RECOVER_RANGE = (10, 900)
CHECK_EVERY = 15        # s : vérification que la vitesse est toujours appliquée


def _call(params, timeout=4):
    url = f"{BASE}/Sensor?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=timeout) as r:
        body = r.read()
    return json.loads(body) if body.strip() else {}


def discover():
    """[(id, nom)] des sorties de ventilateur de la carte mère, pompes exclues."""
    with urllib.request.urlopen(LHM_DATA, timeout=4) as r:
        tree = json.loads(r.read())
    out = []

    def walk(node):
        for child in node.get("Children", []):
            if child.get("Text") == "Controls":
                for s in child.get("Children", []):
                    sid, name = s.get("SensorId", ""), s.get("Text", "")
                    if sid.startswith("/lpc/") and "pump" not in name.lower():
                        out.append((sid, name))
            walk(child)

    walk(tree)
    return out


def _num(text):
    try:
        return float(str(text).split()[0].replace(",", "."))
    except (ValueError, IndexError):
        return None


def read_fans():
    """Tous les ventilateurs vus par LHM : [{name, rpm, pct, pump, gpu, control}] (pct = consigne
    en % si l'appli la force, sinon None)."""
    with urllib.request.urlopen(LHM_DATA, timeout=4) as r:
        tree = json.loads(r.read())
    fans, controls = [], {}

    def walk(node):
        for child in node.get("Children", []):
            group = child.get("Text")
            if group in ("Fans", "Controls"):
                for s in child.get("Children", []):
                    sid = s.get("SensorId", "")
                    if group == "Controls":
                        controls[sid.replace("/control/", "/fan/")] = (sid, _num(s.get("Value")))
                    else:
                        fans.append({"id": sid, "name": s.get("Text", "?"),
                                     "rpm": _num(s.get("Value")) or 0,
                                     "pump": "pump" in s.get("Text", "").lower(),
                                     "gpu": sid.startswith("/gpu")})
            walk(child)

    walk(tree)
    for f in fans:
        ctl = controls.get(f["id"])
        f["control"], f["pct"] = (ctl if ctl else (None, None))
        if f["gpu"]:
            f["name"] = "GPU"
    return fans


class FanControl:
    def __init__(self):
        self.applied = "auto"       # profil réellement appliqué
        self.controls = []
        self.error = ""
        self.event = None           # (titre, détail, horodatage) pour le bandeau
        self.readings = []          # dernière lecture de tous les ventilateurs
        self._want = "auto"
        self.safety = None          # {"profile", "reason", "since"} : auto forcé par la chaleur
        self._cool_since = None
        self._recover_s = RECOVER_SECONDS
        self._quiet_switch = False  # changement dû à la sécurité : son bandeau suffit
        self._last_check = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def update(self, profile, sensors, safe_cpu=SAFE_CPU, safe_gpu=SAFE_GPU_HOTSPOT,
               recover_s=RECOVER_SECONDS):
        """À chaque seconde. Trop chaud : auto forcé temporairement (le réglage n'est pas
        modifié) ; une fois redescendu sous les seuils pendant RECOVER_SECONDS, le profil
        choisi revient. Renvoie True au moment où la sécurité se déclenche."""
        profile = profile if profile in PROFILES else "auto"
        lo, hi = SAFE_RANGE
        safe_cpu = min(hi, max(lo, safe_cpu or SAFE_CPU))
        safe_gpu = min(hi, max(lo, safe_gpu or SAFE_GPU_HOTSPOT))
        self._recover_s = min(RECOVER_RANGE[1], max(RECOVER_RANGE[0], recover_s or RECOVER_SECONDS))
        cpu = sensors.get("cpu_temp") or 0
        hot = sensors.get("hotspot") or sensors.get("temp") or 0
        now = time.time()
        hot_now = cpu >= safe_cpu or hot >= safe_gpu
        if profile in ("auto", "max"):
            self.safety = None                # rien à protéger : profil appliqué tel quel
        elif self.safety is None and hot_now:
            what = f"CPU {cpu:.0f}°C" if cpu >= safe_cpu else f"hotspot GPU {hot:.0f}°C"
            log.warning("ventilateurs : auto forcé (%s), profil %s mis en pause", what,
                        LABELS[profile])
            self.safety = {"profile": profile, "reason": what, "since": now}
            self._cool_since = None
            self.event = ("Ventilateurs en auto", f"sécurité : {what} · {LABELS[profile]} "
                          "reprendra une fois refroidi", now)
            self._want = "auto"
            self._quiet_switch = True
            return True
        elif self.safety is not None:
            cool = cpu < safe_cpu - RECOVER_MARGIN and hot < safe_gpu - RECOVER_MARGIN
            if not cool:
                self._cool_since = None
            elif self._cool_since is None:
                self._cool_since = now
            elif now - self._cool_since >= self._recover_s:
                log.info("ventilateurs : refroidi (CPU %.0f°C), retour au profil %s", cpu,
                         LABELS[profile])
                self.safety = None
                self.event = ("Ventilateurs", f"refroidi : retour au profil {LABELS[profile]}",
                              now)
                self._quiet_switch = True
        self._want = "auto" if self.safety else profile
        return False

    def recovery_left(self):
        """Secondes avant le retour au profil (None : pas encore assez refroidi)."""
        if not self.safety or self._cool_since is None:
            return None
        return max(0.0, self._recover_s - (time.time() - self._cool_since))

    def close(self):
        """Rend les ventilateurs à GCC/BIOS (appelé à la fermeture de l'appli)."""
        self._stop.set()
        with self._lock:
            if self.applied != "auto":
                self._apply("auto")

    # --- fil de travail ---

    def _run(self):
        while not self._stop.is_set():
            try:
                with self._lock:
                    if not self.controls:
                        self.controls = discover()
                    want = self._want
                    if want != self.applied:
                        self._apply(want)
                    elif want != "auto" and time.time() - self._last_check > CHECK_EVERY:
                        self._verify(want)
                self.readings = read_fans()
                self.error = ""
            except Exception as e:
                self.error = "LibreHardwareMonitor injoignable" if "urlopen" in repr(e) or \
                    isinstance(e, OSError) else str(e)
                self.controls = []
            self._stop.wait(1)

    def _apply(self, profile):
        pct = PROFILES[profile]
        for sid, _name in self.controls:
            value = "null" if pct is None else str(max(pct, MIN_PCT))
            _call({"action": "Set", "id": sid, "value": value})
        if profile != self.applied:
            log.info("ventilateurs : %s", LABELS[profile])
            if self._quiet_switch:
                self._quiet_switch = False   # la sécurité a déjà son propre bandeau
            else:
                self.event = ("Ventilateurs", LABELS[profile], time.time())
        self.applied = profile
        self._last_check = time.time()

    def _verify(self, profile):
        """LHM redémarré, ou GCC qui a repris la main : on réapplique."""
        self._last_check = time.time()
        pct = max(PROFILES[profile], MIN_PCT)
        for sid, _name in self.controls:
            if _call({"action": "Get", "id": sid}).get("value") != pct:
                self._apply(profile)
                return
