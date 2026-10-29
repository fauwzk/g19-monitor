"""État des VPN : Tailscale (via sa CLI), autres adaptateurs VPN (OpenVPN, WireGuard…), et IP
publique pour voir par où sort le trafic."""
import json
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import psutil

from .weather import _get

TAILSCALE = shutil.which("tailscale") or r"C:\Program Files\Tailscale\tailscale.exe"
VPN_ADAPTERS = re.compile(r"tailscale|wireguard|openvpn|tap-|wintun|nordlynx|proton|mullvad|"
                          r"vpn|zerotier|cloudflare warp", re.I)
POLL = 5
PUBLIC_IP_EVERY = 300
NO_WINDOW = 0x08000000      # CREATE_NO_WINDOW : pas de console qui clignote
PUBLIC_IP = "https://ipwho.is/?fields=success,ip,city,country,connection"


def _ts(*args, timeout=10):
    return subprocess.run([TAILSCALE, *args], capture_output=True, text=True, timeout=timeout,
                          creationflags=NO_WINDOW, encoding="utf-8", errors="replace")


def _ago(iso):
    """Secondes écoulées depuis une date ISO de Tailscale, ou None."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if dt.year < 2000:
        return None
    return time.time() - dt.timestamp()


class VpnMonitor:
    def __init__(self):
        self.installed = Path(TAILSCALE).exists()
        self.ts = None            # résumé Tailscale, ou None
        self.adapters = []        # [{name, up, ip, rx, tx}]
        self.public = None        # {ip, name, country}
        self.busy = False         # connexion/déconnexion en cours
        self.message = ""
        self._io = {}
        self._t = time.time()
        self._public_t = 0.0
        self._wake = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def toggle(self):
        """Connecte ou déconnecte Tailscale (tailscale up / down)."""
        if not self.installed or self.busy:
            return
        up = not (self.ts and self.ts["running"])

        def work():
            self.busy, self.message = True, "connexion…" if up else "déconnexion…"
            try:
                r = _ts("up" if up else "down", timeout=30)
                self.message = "" if r.returncode == 0 else (r.stderr or r.stdout).strip()[:80]
            except Exception as e:
                self.message = str(e)[:80]
            self.busy = False
            self._public_t = 0          # l'IP publique peut changer (nœud de sortie)
            self._wake.set()

        threading.Thread(target=work, daemon=True).start()

    def _run(self):
        while True:
            try:
                self._poll()
            except Exception:
                pass
            if self._wake.wait(POLL):
                self._wake.clear()

    def _poll(self):
        if self.installed:
            self.ts = self._tailscale()
        self.adapters = self._adapters()
        if time.time() - self._public_t > PUBLIC_IP_EVERY:
            self._public_t = time.time()
            try:
                r = _get(PUBLIC_IP)
                if r.get("success") is not False:
                    self.public = {"ip": r.get("ip", ""), "city": r.get("city", ""),
                                   "country": r.get("country", ""),
                                   "isp": (r.get("connection") or {}).get("isp", "")}
            except Exception:
                pass

    def _tailscale(self):
        try:
            r = _ts("status", "--json")
            d = json.loads(r.stdout)
        except Exception:
            return None
        me = d.get("Self") or {}
        peers = []
        exit_node = None
        for p in (d.get("Peer") or {}).values():
            peer = {"name": p.get("HostName") or p.get("DNSName", "?").split(".")[0],
                    "os": p.get("OS", ""), "online": bool(p.get("Online")),
                    "ip": (p.get("TailscaleIPs") or [""])[0],
                    "direct": bool(p.get("CurAddr")), "active": bool(p.get("Active")),
                    "seen": _ago(p.get("LastSeen", ""))}
            if p.get("ExitNode"):
                exit_node = peer["name"]
            peers.append(peer)
        peers.sort(key=lambda p: (not p["online"], not p["active"], p["name"].lower()))
        state = d.get("BackendState", "")
        return {"state": state, "running": state == "Running",
                "host": me.get("HostName", ""), "ip": (me.get("TailscaleIPs") or [""])[0],
                "tailnet": (d.get("CurrentTailnet") or {}).get("Name", ""),
                "exit": exit_node, "peers": peers,
                "online": sum(p["online"] for p in peers),
                "health": [h for h in d.get("Health") or [] if "stopped" not in h.lower()]}

    def _adapters(self):
        now = time.time()
        dt = max(now - self._t, 1e-3)
        self._t = now
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        io = psutil.net_io_counters(pernic=True)
        out = []
        for name, st in stats.items():
            if not VPN_ADAPTERS.search(name):
                continue
            ip = next((a.address for a in addrs.get(name, []) if a.family.name == "AF_INET"
                       and not a.address.startswith("169.254.")), "")  # 169.254 : pas d'adresse
            c = io.get(name)
            prev = self._io.get(name)
            rx = (c.bytes_recv - prev.bytes_recv) / dt if c and prev else 0.0
            tx = (c.bytes_sent - prev.bytes_sent) / dt if c and prev else 0.0
            if c:
                self._io[name] = c
            out.append({"name": name, "up": st.isup, "ip": ip, "rx": rx, "tx": tx})
        out.sort(key=lambda a: (not a["up"], a["name"].lower()))
        return out


if __name__ == "__main__":
    v = VpnMonitor()
    time.sleep(3)
    ts = v.ts
    print("tailscale:", ts and {k: ts[k] for k in ("state", "host", "ip", "tailnet", "exit", "online")})
    for p in (ts or {}).get("peers", [])[:4]:
        print("  ", p)
    for a in v.adapters:
        print("adaptateur:", a)
    print("public:", v.public)
