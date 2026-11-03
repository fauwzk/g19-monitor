"""Volume, micro, sorties / entrées et volume par appli sous Linux, via pactl (PulseAudio ou
PipeWire). Même interface que volume.VolumeMonitor : la page Audio, la fenêtre de volume et
les profils audio s'en servent tels quels. `pactl subscribe` signale chaque changement, la
fenêtre de volume réagit donc aussitôt."""
import ctypes
import json
import queue
import signal
import subprocess
import threading
import time

from ..volume import STEP, _find, _short, active_profile

REFRESH = 2.0              # s entre deux relectures complètes (sans événement)


def _die_with_parent():
    """Dans le processus enfant : il meurt avec l'appli (sinon `pactl subscribe` resterait
    orphelin à chaque relance)."""
    try:
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGTERM)   # PR_SET_PDEATHSIG
    except OSError:
        pass


def _pactl(*args, timeout=3):
    out = subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        raise OSError(out.stderr.strip() or f"pactl {args[0]} : erreur")
    return out.stdout


def _json(*args):
    return json.loads(_pactl("--format=json", *args) or "[]")


PORT_SEP = "#"             # « sortie#port » : un port de la carte son compte comme un périphérique


def endpoints(entries, default):
    """[(id, nom)] des sorties (ou entrées) et l'id de celle par défaut. Une carte à plusieurs
    ports (haut-parleurs et prise casque d'un portable) donne une ligne par port : choisir
    « Casque audio » règle la sortie par défaut et son port."""
    devs, current = [], None
    for e in entries:
        ports = [p for p in e.get("ports") or [] if p.get("name")]
        if len(ports) < 2:
            devs.append((e["name"], _short(e.get("description") or e["name"])))
            if e["name"] == default:
                current = e["name"]
            continue
        for port in ports:
            dev_id = e["name"] + PORT_SEP + port["name"]
            name = port.get("description") or port["name"]
            if port.get("availability") == "not available":
                name += " (débranché)"
            devs.append((dev_id, name))
            if e["name"] == default and e.get("active_port") == port["name"]:
                current = dev_id
    return devs, current


def set_default(dev_id, inputs=False):
    """Sortie (ou entrée) par défaut, et son port quand il y en a un."""
    verb = "source" if inputs else "sink"
    name, _, port = dev_id.partition(PORT_SEP)
    _pactl(f"set-default-{verb}", name)
    if port:
        _pactl(f"set-{verb}-port", name, port)


def _sources():
    return [s for s in _json("list", "sources") if not s.get("name", "").endswith(".monitor")]


def list_devices():
    """(sorties, entrées) [(id, nom)] pour l'utilitaire, comme volume.list_devices."""
    try:
        outs, _ = endpoints(_json("list", "sinks"), _pactl("get-default-sink").strip())
        ins, _ = endpoints(_sources(), _pactl("get-default-source").strip())
        return outs, ins
    except (OSError, ValueError, subprocess.SubprocessError):
        return [], []


def apply_profile(p):
    """Profil : sortie (et son port), micro, volume. (réussi ?, texte du bandeau)."""
    outputs, inputs = list_devices()
    missing = []
    out = _find(outputs, p.get("out_id"), p.get("out"))
    if out:
        set_default(out)
        vol = p.get("volume")
        if vol is not None:
            _pactl("set-sink-volume", "@DEFAULT_SINK@", f"{int(vol)}%")
            if int(vol) > 0:
                _pactl("set-sink-mute", "@DEFAULT_SINK@", "0")
    elif p.get("out") or p.get("out_id"):
        missing.append("sortie")
    if p.get("in") or p.get("in_id"):
        mic = _find(inputs, p.get("in_id"), p.get("in"))
        if mic:
            set_default(mic, inputs=True)
        else:
            missing.append("micro")
    if missing:
        return False, " et ".join(missing) + " introuvable" + ("s" if len(missing) > 1 else "")
    name = dict(outputs).get(out, p.get("out") or "")
    return True, name or "appliqué"


def _level(entry):
    vols = [int(str(v.get("value_percent", "0")).rstrip("%")) for v in
            (entry.get("volume") or {}).values()]
    return max(vols) / 100 if vols else None


class PulseVolume:
    def __init__(self):
        self.device = ""
        self.level = None
        self.muted = False
        self.peak = 0.0
        self.apps = {}
        self.outputs, self.inputs = [], []
        self.out_id = self.in_id = None
        self.mic_level = None
        self.mic_muted = False
        self.mic_peak = 0.0
        self.mic_device = ""
        self.mic_changed_at = 0.0
        self.changed_at = 0.0
        self.wake = threading.Event()
        self.sessions = []
        self.error = ""
        self.changes = queue.Queue()
        self.profile_events = queue.Queue()
        self._known = None
        self._seen = self._mic_seen = None
        self._inputs_of = {}       # appli → [index des flux]
        self._cmds = queue.Queue()
        self._dirty = threading.Event()
        threading.Thread(target=self._run, daemon=True, name="audio").start()
        threading.Thread(target=self._subscribe, daemon=True, name="audio-événements").start()

    # --- même interface que VolumeMonitor ---

    def app_volume(self, app_name):
        return self.apps.get(app_name.lower())

    def do(self, *cmd):
        self._cmds.put(cmd)
        self._dirty.set()

    def active_profile(self, profiles):
        return active_profile(profiles, self.outputs, self.out_id, self.inputs, self.in_id)

    # --- fils ---

    def _subscribe(self):
        while True:
            try:
                p = subprocess.Popen(["pactl", "subscribe"], stdout=subprocess.PIPE, text=True,
                                     stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     preexec_fn=_die_with_parent)
                for line in p.stdout:
                    if "'change'" in line or "'new'" in line or "'remove'" in line:
                        self._dirty.set()
            except OSError as e:
                self.error = str(e)
            time.sleep(5)

    def _run(self):
        while True:
            try:
                while not self._cmds.empty():
                    self._apply(self._cmds.get_nowait())
                self._refresh()
                self.error = ""
            except (OSError, ValueError, subprocess.SubprocessError) as e:
                self.level = None
                self.error = str(e) or e.__class__.__name__
            self._dirty.wait(REFRESH)
            self._dirty.clear()
            time.sleep(0.03)            # plusieurs événements d'affilée : une seule relecture

    def _refresh(self):
        sinks = _json("list", "sinks")
        sources = _sources()
        default_out = _pactl("get-default-sink").strip()
        default_in = _pactl("get-default-source").strip()
        self.outputs, self.out_id = endpoints(sinks, default_out)
        self.inputs, self.in_id = endpoints(sources, default_in)
        now = {i: (n, "out") for i, n in self.outputs}
        now.update({i: (n, "in") for i, n in self.inputs})
        if self._known is not None:
            for i in now.keys() - self._known.keys():
                self.changes.put((*now[i], True))
            for i in self._known.keys() - now.keys():
                self.changes.put((*self._known[i], False))
        self._known = now

        sink = next((s for s in sinks if s["name"] == default_out), None)
        if sink:
            self.device = dict(self.outputs).get(self.out_id) or sink.get("description") or sink["name"]
            self._level_changed(_level(sink), bool(sink.get("mute")))
        src = next((s for s in sources if s["name"] == default_in), None)
        if src:
            self.mic_device = dict(self.inputs).get(self.in_id) or src.get("description") or src["name"]
            self._mic_changed(_level(src), bool(src.get("mute")))
        else:
            self.mic_level = None

        rows, inputs_of = {}, {}
        for si in _json("list", "sink-inputs"):
            props = si.get("properties") or {}
            name = props.get("application.name") or props.get("media.name") or "?"
            key = name.lower()
            inputs_of.setdefault(key, []).append(si["index"])
            vol = _level(si) or 0.0
            row = rows.setdefault(key, {"key": key, "name": name, "system": False,
                                        "volume": 0.0, "muted": True, "peak": 0.0})
            row["volume"] = max(row["volume"], vol)
            row["muted"] = row["muted"] and bool(si.get("mute"))
        self._inputs_of = inputs_of
        self.apps = {k: r["volume"] for k, r in rows.items()}
        self.sessions = sorted(rows.values(), key=lambda r: r["name"].lower())

    def _level_changed(self, level, muted):
        seen = (self.device, level, muted)
        self.level, self.muted = level, muted
        if self._seen is not None and seen != self._seen and seen[0] == self._seen[0]:
            self.changed_at = time.time()
            self.wake.set()
        self._seen = seen

    def _mic_changed(self, level, muted):
        seen = (self.mic_device, muted)
        self.mic_level, self.mic_muted = level, muted
        if self._mic_seen is not None and seen != self._mic_seen and seen[0] == self._mic_seen[0]:
            self.mic_changed_at = time.time()
            self.wake.set()
        self._mic_seen = seen

    def _apply(self, cmd):
        kind, *args = cmd
        if kind == "default":
            dev = args[0]
            set_default(dev, inputs=any(i == dev for i, _ in self.inputs))
        elif kind == "profile":
            p = args[0]
            try:
                ok, text = apply_profile(p)
            except OSError as e:
                ok, text = False, str(e)
            self.profile_events.put((p.get("name") or "?", ok, text))
        elif kind in ("master", "mic"):
            target = "@DEFAULT_SINK@" if kind == "master" else "@DEFAULT_SOURCE@"
            cur = (self.level if kind == "master" else self.mic_level) or 0.0
            new = min(1.0, max(0.0, round((cur + args[0]) / STEP) * STEP))
            verb = "sink" if kind == "master" else "source"
            _pactl(f"set-{verb}-volume", target, f"{round(new * 100)}%")
            if args[0] > 0:
                _pactl(f"set-{verb}-mute", target, "0")     # monter le volume réactive le son
        elif kind in ("master_mute", "mic_mute"):
            verb, target = (("sink", "@DEFAULT_SINK@") if kind == "master_mute"
                            else ("source", "@DEFAULT_SOURCE@"))
            _pactl(f"set-{verb}-mute", target, "toggle")
        elif kind == "app":
            key, delta = args
            cur = self.apps.get(key, 0.0)
            new = min(1.0, max(0.0, cur + delta))
            for idx in self._inputs_of.get(key, []):
                _pactl("set-sink-input-volume", str(idx), f"{round(new * 100)}%")
                if new > 0:
                    _pactl("set-sink-input-mute", str(idx), "0")
        elif kind == "app_mute":
            for idx in self._inputs_of.get(args[0], []):
                _pactl("set-sink-input-mute", str(idx), "toggle")
