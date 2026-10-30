"""Bandeau à la connexion d'un périphérique (USB, Bluetooth, audio) : Windows prévient une
fenêtre invisible (WM_DEVICECHANGE), on retrouve le nom de l'appareil, et sa batterie s'il en
a une (via battery.Batteries)."""
import ctypes
import json
import re
import subprocess
import threading
import time
from ctypes import wintypes

WM_DEVICECHANGE = 0x0219
DBT_DEVICEARRIVAL = 0x8000
DBT_DEVTYP_DEVICEINTERFACE = 5
DEVICE_NOTIFY_ALL_INTERFACE_CLASSES = 4
HWND_MESSAGE = wintypes.HWND(-3)
DEBOUNCE = 2.0          # s : un appareil arrive en plusieurs interfaces d'un coup
BATTERY_WAIT = 20       # s pendant lesquels la batterie peut compléter le bandeau

# classes d'appareils qui valent un bandeau (le reste : bus, interfaces logicielles…)
# (l'audio est suivi à part, connexions et déconnexions : voir DeviceWatcher.audio)
CLASSES = {"bluetooth", "mouse", "keyboard", "image", "camera", "wpd",
           "diskdrive", "media", "hidclass", "xboxcomposite", "xnacomposite", "monitor",
           "printer", "net"}
GENERIC = re.compile(r"(compliant|composite|root hub|concentrateur|périphérique d.entrée|"
                     r"input device|usb hub|generic|générique|enumerator|énumérateur|"
                     r"virtual|virtuel|^\s*$)", re.I)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                             wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]


class DEV_BROADCAST_DEVICEINTERFACE(ctypes.Structure):
    _fields_ = [("dbcc_size", wintypes.DWORD), ("dbcc_devicetype", wintypes.DWORD),
                ("dbcc_reserved", wintypes.DWORD), ("dbcc_classguid", ctypes.c_byte * 16),
                ("dbcc_name", ctypes.c_wchar * 1)]


user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                   wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                   wintypes.HINSTANCE, wintypes.LPVOID]
user32.RegisterDeviceNotificationW.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD]
user32.RegisterDeviceNotificationW.restype = wintypes.HANDLE
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT,
                               wintypes.UINT]


GENERIC_KIND = re.compile(r"^(haut-parleurs|casque|écouteurs|microphone|micro|speakers|"
                          r"headphones|headset|entrée ligne|line in|sortie numérique)$", re.I)


# PowerShell écrit dans la page de code de la console : sans ça, « Entrée » devient « Entr‚e »
UTF8 = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "


def _core(name):
    """Le nom de l'appareil : « Casque · WH-1000XM4 Hands-Free (+1) » → « WH-1000XM4 »,
    « ASUS VG278HE · HDMI » → « ASUS VG278HE »."""
    name = re.sub(r"\s*\(\+\d+\)$", "", name)
    kind, sep, rest = name.partition("·")
    name = rest.strip() if sep and GENERIC_KIND.match(kind.strip()) else kind.strip()
    return re.sub(r"\s+(Hands-Free|Mains libres|Stereo)$", "", name, flags=re.I).strip()


def instance_id(path):
    """\\\\?\\USB#VID_046D&PID_C52B#123#{guid} → USB\\VID_046D&PID_C52B\\123"""
    p = path[4:] if path.startswith("\\\\?\\") else path
    p = re.sub(r"#\{[0-9a-fA-F-]+\}$", "", p)
    return p.replace("#", "\\")


class DeviceWatcher:
    def __init__(self, batteries=None):
        self.batteries = batteries
        self.event = None        # (titre, texte, horodatage) pour le bandeau
        self._pending = []
        self._last = 0.0
        self._recent = {}        # nom → horodatage (pas deux bandeaux pour le même appareil)
        self._proc = WNDPROC(self._wndproc)   # gardé en vie : référencé par la classe Win32
        threading.Thread(target=self._window, daemon=True).start()
        threading.Thread(target=self._worker, daemon=True).start()

    # --- fenêtre invisible qui reçoit les arrivées d'appareils ---

    def _window(self):
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW(lpfnWndProc=self._proc, hInstance=hinst, lpszClassName="G19DeviceWatch")
        user32.RegisterClassW(ctypes.byref(wc))
        hwnd = user32.CreateWindowExW(0, "G19DeviceWatch", "G19", 0, 0, 0, 0, 0, HWND_MESSAGE,
                                      None, hinst, None)
        f = DEV_BROADCAST_DEVICEINTERFACE(dbcc_size=ctypes.sizeof(DEV_BROADCAST_DEVICEINTERFACE),
                                          dbcc_devicetype=DBT_DEVTYP_DEVICEINTERFACE)
        user32.RegisterDeviceNotificationW(hwnd, ctypes.byref(f),
                                           DEVICE_NOTIFY_ALL_INTERFACE_CLASSES)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_DEVICECHANGE and wparam == DBT_DEVICEARRIVAL and lparam:
            hdr = DEV_BROADCAST_DEVICEINTERFACE.from_address(lparam)
            if hdr.dbcc_devicetype == DBT_DEVTYP_DEVICEINTERFACE:
                name = ctypes.wstring_at(lparam + DEV_BROADCAST_DEVICEINTERFACE.dbcc_name.offset)
                self._pending.append(instance_id(name))
                self._last = time.time()
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # --- identification des appareils arrivés ---

    def _worker(self):
        while True:
            time.sleep(0.5)
            if self._pending and time.time() - self._last >= DEBOUNCE:
                ids, self._pending = list(dict.fromkeys(self._pending)), []
                try:
                    self._announce(self._resolve(ids))
                except Exception:
                    pass
            try:
                self._complete_battery()
            except Exception:
                pass

    @staticmethod
    def _resolve(ids):
        script = (UTF8 + "$ids = ConvertFrom-Json $env:G19_IDS; @(foreach ($i in $ids) {"
                  " Get-PnpDevice -InstanceId $i -ErrorAction SilentlyContinue |"
                  " Select-Object FriendlyName, Class, InstanceId }) | ConvertTo-Json -Compress")
        import os
        env = {**os.environ, "G19_IDS": json.dumps(ids[:40])}
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=30, env=env,
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout.strip()
        data = json.loads(out) if out else []
        return [data] if isinstance(data, dict) else data

    def _announce(self, devices):
        now = time.time()
        names = []
        for d in devices:
            name = (d.get("FriendlyName") or "").strip()
            cls = (d.get("Class") or "").lower()
            if cls not in CLASSES or GENERIC.search(name):
                continue
            # « Casque (WH-1000XM4) » → « WH-1000XM4 » pour l'audio : plus lisible
            m = re.match(r"^[^(]+\((.+)\)$", name)
            if cls == "audioendpoint" and m:
                name = m.group(1)
            if now - self._recent.get(name.lower(), 0) < 30 or name in names:
                continue
            names.append(name)
        if not names:
            return
        for n in names:
            self._recent[n.lower()] = now
        title = names[0] if len(names) == 1 else f"{names[0]} (+{len(names) - 1})"
        self.event = (title, "connecté", now)
        if self.batteries:
            self.batteries.refresh()

    def audio(self, changes):
        """Périphériques audio apparus / disparus : [(nom, "out"|"in", connecté ?)]. Un casque
        arrive en plusieurs entrées (casque, mains libres, micro) : un seul bandeau."""
        now = time.time()
        for connected in (True, False):
            group = [(n, flow) for n, flow, c in changes if c == connected]
            if not group:
                continue
            cores = list(dict.fromkeys(_core(n) for n, _ in group))
            kinds = sorted({"sortie" if flow == "out" else "micro" for _, flow in group},
                           reverse=True)
            title = cores[0] if len(cores) == 1 else f"{cores[0]} (+{len(cores) - 1})"
            body = ("connecté" if connected else "déconnecté") + " · " + " et ".join(kinds)
            ev = self.event
            if ev and now - ev[2] < 10 and _core(ev[0]) == _core(title) and                     ev[1].startswith(body.split(" ·")[0]):
                continue          # même appareil déjà annoncé (par l'USB / Bluetooth)
            self.event = (title, body, now)
            self._recent[title.lower()] = now
            if connected and self.batteries:
                self.batteries.refresh()

    def _complete_battery(self):
        """Ajoute le pourcentage au bandeau dès que la batterie de l'appareil est connue."""
        ev = self.event
        if (not ev or not ev[1].startswith("connecté") or "batterie" in ev[1]
                or time.time() - ev[2] > BATTERY_WAIT or not self.batteries):
            return
        title = _core(ev[0]).lower()
        for dev in self.batteries.devices:
            n = dev["name"].lower()
            if n in title or title in n:
                self.event = (ev[0], f"{ev[1]} · batterie {dev['level']} %", ev[2])
                return
