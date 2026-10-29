"""Réseau en jeu : un ping par seconde vers une cible (ICMP de Windows, sans droits admin),
latence / gigue / perte sur la dernière minute, et alerte sur un pic ou des pertes."""
import collections
import ctypes
import socket
import statistics
import struct
import threading
import time
from ctypes import wintypes

KEEP = 120
TIMEOUT_MS = 1000
REALERT = 60

iphlpapi = ctypes.WinDLL("iphlpapi")
iphlpapi.IcmpCreateFile.restype = wintypes.HANDLE
iphlpapi.IcmpSendEcho.argtypes = [wintypes.HANDLE, wintypes.ULONG, ctypes.c_void_p, wintypes.WORD,
                                  ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD]
iphlpapi.IcmpSendEcho.restype = wintypes.DWORD


class ICMP_ECHO_REPLY(ctypes.Structure):
    _fields_ = [("Address", wintypes.ULONG), ("Status", wintypes.ULONG),
                ("RoundTripTime", wintypes.ULONG), ("DataSize", wintypes.WORD),
                ("Reserved", wintypes.WORD), ("Data", ctypes.c_void_p),
                ("Ttl", ctypes.c_ubyte), ("Tos", ctypes.c_ubyte), ("Flags", ctypes.c_ubyte),
                ("OptionsSize", ctypes.c_ubyte), ("OptionsData", ctypes.c_void_p)]


class Pinger:
    def __init__(self, target_fn):
        self.target_fn = target_fn
        self.target = ""
        self.samples = collections.deque(maxlen=KEEP)   # ms, ou None si perdu
        self.status = "démarrage…"
        self.event = None          # (titre, texte, horodatage) pour le bandeau
        self._alerted = 0.0
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        handle = iphlpapi.IcmpCreateFile()
        payload = ctypes.create_string_buffer(b"G19Monitor" * 3)
        reply = ctypes.create_string_buffer(ctypes.sizeof(ICMP_ECHO_REPLY) + len(payload) + 8)
        addr, resolved_for = None, None
        while True:
            start = time.time()
            target = (self.target_fn() or "1.1.1.1").strip()
            try:
                if target != resolved_for:
                    ip = socket.gethostbyname(target)
                    addr = struct.unpack("<I", socket.inet_aton(ip))[0]
                    resolved_for, self.target = target, target if target == ip else f"{target} ({ip})"
                    self.samples.clear()
                n = iphlpapi.IcmpSendEcho(handle, addr, payload, len(payload), None, reply,
                                          len(reply), TIMEOUT_MS)
                r = ICMP_ECHO_REPLY.from_buffer(reply)
                self.samples.append(float(r.RoundTripTime) if n and r.Status == 0 else None)
                self.status = ""
            except OSError:
                self.status = f"cible introuvable : {target}"
                resolved_for = None
                self.samples.append(None)
            time.sleep(max(0.0, 1.0 - (time.time() - start)))

    def stats(self, window=60):
        """{"last", "avg", "min", "max", "jitter", "loss"} sur les `window` dernières mesures."""
        recent = list(self.samples)[-window:]
        ok = [v for v in recent if v is not None]
        out = {"last": recent[-1] if recent else None, "count": len(recent)}
        out["loss"] = (1 - len(ok) / len(recent)) * 100 if recent else 0.0
        if ok:
            out.update(avg=statistics.mean(ok), min=min(ok), max=max(ok),
                       jitter=statistics.mean(abs(a - b) for a, b in zip(ok, ok[1:]))
                       if len(ok) > 1 else 0.0)
        return out

    def check_alert(self, in_game, now):
        """Pendant une partie : bandeau sur un pic de latence ou des pertes répétées."""
        if not in_game or now - self._alerted < REALERT or len(self.samples) < 10:
            return
        recent = list(self.samples)[-10:]
        ok = [v for v in recent if v is not None]
        lost = len(recent) - len(ok)
        base = statistics.median(ok) if ok else 0
        last = recent[-1]
        if lost >= 3:
            self.event = ("Réseau", f"{lost} paquets perdus sur 10 s", now)
        elif last is not None and last > max(100.0, base * 3):
            self.event = ("Réseau", f"pic de latence : {last:.0f} ms (habituel {base:.0f} ms)", now)
        else:
            return
        self._alerted = now
