"""Test de débit (ping, gigue, descendant, montant) sur les serveurs de speed.cloudflare.com."""
import http.client
import os
import statistics
import threading
import time

from . import config

HOST = "speed.cloudflare.com"
HISTORY_FILE = "speedtest.json"   # 20 derniers, pour l'écran
LOG_FILE = "speedtests.csv"       # tous les tests, ouvrable dans Excel
EOL = "\r\n"                      # fins de ligne Windows, pour Excel
STREAMS = 4               # connexions parallèles
PHASE_SECONDS = 8         # durée du test descendant / montant
WARMUP = 1.0              # s ignorées au début (montée en charge TCP)
PINGS = 12
DOWN_CHUNK = 50_000_000   # octets demandés par requête
UP_CHUNK = 8_000_000
UA = {"User-Agent": "G19Monitor speedtest"}


def log_result(r):
    """Ajoute un test à speedtests.csv (séparateur « ; » et virgule décimale, pour Excel)."""
    path = config.DATA_DIR / LOG_FILE

    def num(v, fmt="{:.1f}"):
        return fmt.format(v).replace(".", ",") if v is not None else ""

    new = not path.exists()
    try:
        with open(path, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
            if new:
                f.write("date;ping (ms);gigue (ms);descendant (Mb/s);montant (Mb/s);serveur" + EOL)
            f.write(";".join([time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["time"])),
                              num(r["ping"]), num(r["jitter"]), num(r["down"]), num(r["up"]),
                              r.get("server") or ""]) + EOL)
    except OSError:
        pass


class Cancelled(Exception):
    pass


class SpeedTest:
    def __init__(self):
        self.phase = "idle"       # idle / ping / download / upload / done / error
        self.live = 0.0           # Mbit/s instantané
        self.progress = 0.0       # avancement de la phase 0..1
        self.ping = self.jitter = self.down = self.up = None
        self.server = ""
        self.error = ""
        self.peak = 0.0
        self.history = config.load(HISTORY_FILE, []) or []
        if self.history and not (config.DATA_DIR / LOG_FILE).exists():
            for r in reversed(self.history):   # reprise des tests déjà faits
                log_result(r)
        self._cancel = threading.Event()
        self._thread = None

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def toggle(self):
        if self.running:
            self._cancel.set()
        else:
            self.start()

    def start(self):
        if self.running:
            return
        self._cancel.clear()
        self.ping = self.jitter = self.down = self.up = None
        self.error, self.peak, self.live = "", 0.0, 0.0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # --- déroulé ---

    def _run(self):
        try:
            self.phase = "ping"
            self._meta()
            self._ping()
            self.phase = "download"
            self.down = self._transfer(self._download_worker)
            self.phase = "upload"
            self.up = self._transfer(self._upload_worker)
            self.phase = "done"
            self.history.insert(0, {"time": time.time(), "ping": self.ping, "jitter": self.jitter,
                                    "down": self.down, "up": self.up, "server": self.server})
            del self.history[20:]
            config.save(HISTORY_FILE, self.history)
            log_result(self.history[0])
        except Cancelled:
            self.phase, self.error = "error", "annulé"
        except Exception as e:
            self.phase, self.error = "error", str(e) or e.__class__.__name__
        self.live = 0.0

    def _check(self):
        if self._cancel.is_set():
            raise Cancelled()

    @staticmethod
    def _conn():
        return http.client.HTTPSConnection(HOST, timeout=10)

    def _meta(self):
        c = self._conn()
        c.request("GET", "/cdn-cgi/trace", headers=UA)
        info = dict(line.split("=", 1) for line in c.getresponse().read().decode().splitlines()
                    if "=" in line)
        c.close()
        self.server = info.get("colo", "")

    def _ping(self):
        c = self._conn()
        rtts = []
        c.request("GET", "/__down?bytes=0", headers=UA)  # établit la connexion TLS
        c.getresponse().read()
        for i in range(PINGS):
            self._check()
            t0 = time.perf_counter()
            c.request("GET", "/__down?bytes=0", headers=UA)
            r = c.getresponse()
            r.read()
            rtt = (time.perf_counter() - t0) * 1000
            # Cloudflare indique son temps de traitement : on le retire du RTT
            timing = r.getheader("server-timing", "")
            if "dur=" in timing:
                try:
                    rtt -= float(timing.split("dur=")[1].split(",")[0].split(";")[0])
                except ValueError:
                    pass
            rtts.append(max(rtt, 0.1))
            self.progress = (i + 1) / PINGS
            self.ping = statistics.median(rtts)
        c.close()
        self.jitter = statistics.mean(abs(a - b) for a, b in zip(rtts, rtts[1:])) if len(rtts) > 1 else 0

    def _transfer(self, worker):
        """Lance STREAMS workers pendant PHASE_SECONDS ; renvoie le débit moyen en Mbit/s."""
        counts = [0] * STREAMS
        deadline = time.perf_counter() + PHASE_SECONDS
        threads = [threading.Thread(target=self._safe, args=(worker, counts, i, deadline),
                                    daemon=True) for i in range(STREAMS)]
        start = time.perf_counter()
        for t in threads:
            t.start()
        samples, warm_bytes, last = [], None, (start, 0)
        while time.perf_counter() < deadline:
            time.sleep(0.25)
            if self._cancel.is_set():
                break
            now, total = time.perf_counter(), sum(counts)
            self.live = (total - last[1]) * 8 / (now - last[0]) / 1e6
            last = (now, total)
            samples.append(self.live)
            self.peak = max(self.peak, self.live)
            self.progress = min((now - start) / PHASE_SECONDS, 1.0)
            if warm_bytes is None and now - start >= WARMUP:
                warm_bytes = (now, total)
        for t in threads:
            t.join(timeout=3)
        self._check()
        end, total = time.perf_counter(), sum(counts)
        t0, b0 = warm_bytes or (start, 0)
        if total == 0:
            raise RuntimeError("aucune donnée transférée")
        return (total - b0) * 8 / max(end - t0, 1e-3) / 1e6

    def _safe(self, worker, counts, i, deadline):
        try:
            worker(counts, i, deadline)
        except Exception:
            pass

    def _download_worker(self, counts, i, deadline):
        c = self._conn()
        while time.perf_counter() < deadline and not self._cancel.is_set():
            c.request("GET", f"/__down?bytes={DOWN_CHUNK}", headers=UA)
            r = c.getresponse()
            while time.perf_counter() < deadline and not self._cancel.is_set():
                chunk = r.read(65536)
                if not chunk:
                    break
                counts[i] += len(chunk)
            if not r.isclosed():
                c.close()           # requête interrompue : nouvelle connexion
                c = self._conn()
        c.close()

    def _upload_worker(self, counts, i, deadline):
        block = os.urandom(65536)
        c = self._conn()
        while time.perf_counter() < deadline and not self._cancel.is_set():
            c.putrequest("POST", "/__up")
            c.putheader("Content-Length", str(UP_CHUNK))
            c.putheader("Content-Type", "application/octet-stream")
            c.putheader("User-Agent", UA["User-Agent"])
            c.endheaders()
            sent = 0
            while sent < UP_CHUNK and time.perf_counter() < deadline and not self._cancel.is_set():
                n = min(len(block), UP_CHUNK - sent)
                c.send(block[:n])
                sent += n
                counts[i] += n
            if sent < UP_CHUNK:
                break
            c.getresponse().read()
        c.close()
