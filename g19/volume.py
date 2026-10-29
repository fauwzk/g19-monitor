"""Audio du système via Core Audio (pycaw) : sortie et entrée par défaut (et leur choix), volume
général, micro, volume par appli, vumètres. Les réglages s'appliquent directement à Windows.

Tout l'accès COM se fait dans un seul thread ; l'écran envoie ses commandes par `do()`."""
import queue
import threading
import time
import warnings

try:
    import comtypes
    from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
    from pycaw.constants import ERole
except ImportError:
    AudioUtilities = None

CLSCTX_ALL = 23
RENDER, CAPTURE = 0, 1
DEVICE_STATE_ACTIVE = 1
STEP = 0.05               # pas de réglage des volumes

# nom affiché par la page média → exécutables possibles
MEDIA_APPS = {"spotify": ("spotify",), "chrome": ("chrome",), "edge": ("msedge",),
              "firefox": ("firefox",), "vlc": ("vlc",), "deezer": ("deezer",),
              "navigateur": ("firefox", "chrome", "msedge", "opera", "brave"),
              "lecteur multimédia": ("microsoft.media.player",), "apple music": ("applemusic",)}

# exécutable → nom affiché sur l'écran audio
APP_NAMES = {"spotify": "Spotify", "chrome": "Chrome", "msedge": "Edge", "firefox": "Firefox",
             "discord": "Discord", "steam": "Steam", "steamwebhelper": "Steam", "vlc": "VLC",
             "teams": "Teams", "ms-teams": "Teams", "zoom": "Zoom", "obs64": "OBS",
             "applemusic": "Apple Music", "deezer": "Deezer", "opera": "Opera", "brave": "Brave",
             "microsoft.media.player": "Lecteur multimédia", "svchost": "Services Windows",
             "gamebar": "Game Bar", "lghub_agent": "G HUB", "thunderbird": "Thunderbird",
             "": "Sons système"}


def _unit(v):
    """Volume ou crête ramené dans 0..1 (certains pilotes renvoient un peu plus de 1)."""
    try:
        return min(1.0, max(0.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def _short(name):
    """« Haut-parleurs (Realtek(R) Audio) » → « Haut-parleurs · Realtek Audio »."""
    name = (name or "?").replace("(R)", "").replace("(TM)", "")
    if "(" in name and name.endswith(")"):
        kind, _, rest = name.partition("(")
        kind, rest = kind.strip(), rest[:-1].strip()
        # sortie HDMI / DisplayPort d'un écran : « 2 - ASUS VG278HE » → « ASUS VG278HE · HDMI »
        if "High Definition Audio" in rest and " - " in kind[:4]:
            return f"{kind.split(' - ', 1)[1]} · HDMI"
        return f"{kind} · {rest}"
    return name


class VolumeMonitor:
    def __init__(self):
        self.device = ""
        self.level = None        # sortie par défaut, 0..1, None si inconnu
        self.muted = False
        self.peak = 0.0          # niveau instantané 0..1
        self.apps = {}           # exe sans extension (minuscules) → volume 0..1
        self.outputs = []        # [(id, nom court)] sorties actives
        self.inputs = []         # [(id, nom court)] entrées actives
        self.out_id = self.in_id = None
        self.mic_level = None
        self.mic_muted = False
        self.mic_peak = 0.0
        self.sessions = []       # [{"key", "name", "system", "volume", "muted", "peak"}] par appli
        self.error = ""
        self.changes = queue.Queue()   # (nom, "out"|"in", connecté ?) : périphériques audio
        self._known = None             # {id: (nom, sens)} au dernier passage (None : premier)
        self._cmds = queue.Queue()
        self._live = {}          # nom d'appli → [sessions COM] (dans le thread audio)
        if AudioUtilities:
            threading.Thread(target=self._run, daemon=True).start()

    def app_volume(self, app_name):
        for exe in MEDIA_APPS.get(app_name.lower(), (app_name.lower(),)):
            if exe in self.apps:
                return self.apps[exe]
        return None

    def do(self, *cmd):
        """Commande pour le thread audio : ("default", id), ("master", ±pas), ("master_mute",),
        ("mic", ±pas), ("mic_mute",), ("app", nom, ±pas), ("app_mute", nom)."""
        self._cmds.put(cmd)

    # --- thread audio ---

    def _run(self):
        comtypes.CoInitialize()
        warnings.filterwarnings("ignore", module="pycaw")
        self._meters = []
        last = 0.0
        while True:
            try:
                dirty = False
                while not self._cmds.empty():
                    self._apply(self._cmds.get_nowait())
                    dirty = True
                now = time.time()
                if dirty or now - last >= 1:   # la sortie par défaut peut changer (casque…)
                    last = now
                    self._refresh()
                self._read_peaks()
                self.error = ""
            except Exception as e:
                self._meters, self.level = [], None
                self.error = str(e) or e.__class__.__name__
                time.sleep(2)
            time.sleep(0.08)

    def _endpoints(self, flow):
        enum = AudioUtilities.GetDeviceEnumerator()
        coll = enum.EnumAudioEndpoints(flow, DEVICE_STATE_ACTIVE)
        out = []
        for i in range(coll.GetCount()):
            dev = AudioUtilities.CreateDevice(coll.Item(i))
            out.append((dev.id, _short(dev.FriendlyName)))
        out.sort(key=lambda d: d[1].lower())
        try:
            default = enum.GetDefaultAudioEndpoint(flow, ERole.eMultimedia.value).GetId()
        except Exception:
            default = None
        return out, default

    @staticmethod
    def _meter(imm):
        return imm.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None) \
            .QueryInterface(IAudioMeterInformation)

    def _refresh(self):
        self.outputs, self.out_id = self._endpoints(RENDER)
        self.inputs, self.in_id = self._endpoints(CAPTURE)
        # périphériques audio apparus / disparus depuis le passage précédent
        now = {i: (n, "out") for i, n in self.outputs}
        now.update({i: (n, "in") for i, n in self.inputs})
        if self._known is not None:
            for i in now.keys() - self._known.keys():
                self.changes.put((*now[i], True))
            for i in self._known.keys() - now.keys():
                self.changes.put((*self._known[i], False))
        self._known = now
        meters = []
        spk = AudioUtilities.GetSpeakers()
        ev = spk.EndpointVolume
        self.device = spk.FriendlyName or ""
        self.level = _unit(ev.GetMasterVolumeLevelScalar())
        self.muted = bool(ev.GetMute())
        meters.append(("out", self._meter(spk._dev)))
        mic = AudioUtilities.GetMicrophone()
        if mic:
            dev = AudioUtilities.CreateDevice(mic)
            mev = dev.EndpointVolume
            self.mic_level = _unit(mev.GetMasterVolumeLevelScalar())
            self.mic_muted = bool(mev.GetMute())
            meters.append(("mic", self._meter(mic)))
        else:
            self.mic_level = None
        apps, live, rows = {}, {}, {}
        for s in AudioUtilities.GetAllSessions():
            exe = s.Process.name().lower().removesuffix(".exe") if s.Process else ""
            if s.Process is None and not s.DisplayName.startswith("@%SystemRoot%"):
                continue        # sessions sans processus autres que les sons système
            vol = s.SimpleAudioVolume
            # une ligne par appli affichée (Steam + steamwebhelper → « Steam »)
            name = APP_NAMES.get(exe) or exe.replace("_", " ").replace("-", " ").title()
            live.setdefault(name, []).append(s)
            row = rows.setdefault(name, {"key": name, "name": name, "system": exe == "",
                                         "volume": 0.0, "muted": True, "peak": 0.0})
            row["volume"] = max(row["volume"], _unit(vol.GetMasterVolume()))
            row["muted"] = row["muted"] and bool(vol.GetMute())
            if exe:
                apps[exe] = max(apps.get(exe, 0.0), row["volume"])
            try:
                meters.append(("app:" + name, s._ctl.QueryInterface(IAudioMeterInformation)))
            except Exception:
                pass
        self.apps, self._live = apps, live
        # appli la plus bruyante en premier, sons système à la fin
        self.sessions = sorted(rows.values(), key=lambda r: (r["system"], r["name"].lower()))
        self._meters = meters

    def _read_peaks(self):
        peaks = {}
        for key, meter in self._meters:
            try:
                peaks[key] = max(peaks.get(key, 0.0), _unit(meter.GetPeakValue()))
            except Exception:
                pass
        self.peak = peaks.get("out", 0.0)
        self.mic_peak = peaks.get("mic", 0.0)
        for row in self.sessions:
            row["peak"] = peaks.get("app:" + row["key"], 0.0)

    def _apply(self, cmd):
        kind, *args = cmd
        if kind == "default":
            AudioUtilities.SetDefaultDevice(args[0], [ERole.eConsole, ERole.eMultimedia,
                                                      ERole.eCommunications])
        elif kind in ("master", "master_mute"):
            ev = AudioUtilities.GetSpeakers().EndpointVolume
            self._change(ev.GetMasterVolumeLevelScalar, ev.SetMasterVolumeLevelScalar,
                         ev.GetMute, ev.SetMute, kind, args)
        elif kind in ("mic", "mic_mute"):
            mic = AudioUtilities.GetMicrophone()
            if mic:
                ev = AudioUtilities.CreateDevice(mic).EndpointVolume
                self._change(ev.GetMasterVolumeLevelScalar, ev.SetMasterVolumeLevelScalar,
                             ev.GetMute, ev.SetMute, kind, args)
        elif kind in ("app", "app_mute"):
            key, *rest = args
            sessions = self._live.get(key, [])
            if kind == "app":
                cur = max((s.SimpleAudioVolume.GetMasterVolume() for s in sessions), default=0)
                new = min(1.0, max(0.0, cur + rest[0]))
                for s in sessions:
                    s.SimpleAudioVolume.SetMasterVolume(new, None)
                    if new > 0:
                        s.SimpleAudioVolume.SetMute(0, None)
            else:
                mute = not all(s.SimpleAudioVolume.GetMute() for s in sessions)
                for s in sessions:
                    s.SimpleAudioVolume.SetMute(int(mute), None)

    @staticmethod
    def _change(get, set_, get_mute, set_mute, kind, args):
        if kind.endswith("_mute"):
            set_mute(0 if get_mute() else 1, None)
            return
        new = min(1.0, max(0.0, round((get() + args[0]) / STEP) * STEP))
        set_(new, None)
        if get_mute() and args[0] > 0:
            set_mute(0, None)       # monter le volume réactive le son
