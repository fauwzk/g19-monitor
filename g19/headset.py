"""Batterie des casques sans fil HyperX branchés par leur dongle USB (pas en Bluetooth : Windows
ne connaît pas leur niveau, seul NGENUITY le lit), par le protocole HID du dongle.

HyperX Cloud III S Wireless (HP 03F0:02CC / 06BE) : protocole décodé à partir de captures de
NGENUITY (projet HyperHeadset, puis HaloBattery). Une demande de *lecture* en rapport de
sortie 0x0C sur l'interface 3 :
    0c 02 03 01 00 <cmd> 00…     (octet 3 = 01 : lire ; jamais 00, qui écrirait un réglage)
    cmd 0x06 batterie (%), 0x48 charge (0 non, 1 en charge, 2 chargé)
réponse en rapport d'entrée 0x0C : octet 5 = cmd, octet 6 = valeur (0xFF : pas de valeur,
casque éteint ou hors de portée). Le casque envoie aussi de lui-même des notifications 0x0D :
octet 4 = 1 → batterie en octet 5, octet 4 = 10 → état de charge en octet 5.
Windows découpe l'interface en plusieurs collections : la demande part vers la première qui
accepte le rapport 0x0C, la réponse peut arriver sur une autre, on les lit toutes."""
import threading
import time

try:
    import hid
except ImportError:
    hid = None

VID = 0x03F0
MODELS = {0x02CC: "HyperX Cloud III S", 0x06BE: "HyperX Cloud III S"}
REPORT, NOTE = 0x0C, 0x0D
CMD_BATTERY, CMD_CHARGING = 0x06, 0x48
EVERY = 60               # s entre deux demandes ; les notifications arrivent entre-temps
WAIT = 1.5               # s d'attente d'une réponse


def _request(cmd):
    return [REPORT, 0x02, 0x03, 0x01, 0x00, cmd] + [0] * 58


def parse(r):
    """Rapport d'entrée → ("battery", %) ou ("charging", état), sinon None."""
    if not r or len(r) < 7:
        return None
    if r[0] == REPORT and r[5] in (CMD_BATTERY, CMD_CHARGING):
        v = r[6]
        if r[5] == CMD_BATTERY:
            return ("battery", v) if v <= 100 else ("off", None)
        return ("charging", v) if v != 0xFF else ("off", None)
    if r[0] == NOTE:
        if r[4] == 1 and r[5] <= 100:
            return "battery", r[5]
        if r[4] == 10:
            return "charging", r[5]
    return None


class HyperXBattery:
    def __init__(self, on_change=None):
        self.name = None          # modèle trouvé, None : aucun dongle branché
        self.level = None
        self.charging = None
        self.connected = False    # casque allumé et relié au dongle
        self.on_change = on_change
        self._handles = []
        self._writer = None
        if hid:
            threading.Thread(target=self._run, daemon=True, name="casque").start()

    def device(self):
        """Entrée pour la page Batteries, ou None."""
        if not self.name or self.level is None:
            return None
        return {"name": self.name, "level": self.level, "connected": self.connected,
                "charging": bool(self.charging in (1, 2) and self.connected)}

    # --- fil de lecture ---

    def _open(self):
        self._close()
        found = [d for d in hid.enumerate(VID) if d["product_id"] in MODELS]
        self.name = MODELS[found[0]["product_id"]] if found else None
        # pages constructeur d'abord : c'est l'une d'elles qui prend la demande
        for d in sorted(found, key=lambda d: (0 if d["usage_page"] >= 0xFF00 else 1,
                                              d["usage_page"])):
            h = hid.device()
            try:
                h.open_path(d["path"])
                h.set_nonblocking(True)
                self._handles.append(h)
            except (OSError, IOError):
                continue

    def _close(self):
        for h in self._handles:
            try:
                h.close()
            except Exception:
                pass
        self._handles, self._writer = [], None

    def _send(self, cmd):
        for h in ([self._writer] if self._writer else []) + self._handles:
            try:
                n = h.write(_request(cmd))
            except (OSError, IOError, ValueError):
                n = -1
            if n is not None and n >= 0:
                self._writer = h
                return True
        return False

    def _drain(self, until, want=None):
        """Lit toutes les collections jusqu'à `until` (ou jusqu'à la réponse `want`)."""
        while time.time() < until:
            got = False
            for h in self._handles:
                try:
                    r = h.read(64)
                except (OSError, IOError, ValueError):
                    raise
                if r:
                    got = True
                    p = parse(r)
                    if p:
                        self._apply(*p)
                        if want and p[0] in (want, "off"):
                            return True
            if not got:
                time.sleep(0.05 if want else 0.25)
        return False

    def _apply(self, kind, value):
        before = (self.level, self.charging, self.connected)
        if kind == "off":
            self.connected = False
        elif kind == "battery":
            self.level, self.connected = value, True
        elif kind == "charging":
            self.charging = value
        if before != (self.level, self.charging, self.connected) and self.on_change:
            self.on_change()

    def _run(self):
        while True:
            try:
                self._open()
                if not self._handles:
                    self.connected = False
                    time.sleep(30)          # dongle débranché : on regarde de temps en temps
                    continue
                while True:
                    for cmd, kind in ((CMD_BATTERY, "battery"), (CMD_CHARGING, "charging")):
                        if self._send(cmd) and not self._drain(time.time() + WAIT, kind)                                 and kind == "battery":
                            self._apply("off", None)    # pas de réponse : casque éteint
                    self._drain(time.time() + EVERY)     # notifications entre deux demandes
            except Exception:
                self._close()
                time.sleep(10)              # dongle retiré pendant la lecture : on rouvre
