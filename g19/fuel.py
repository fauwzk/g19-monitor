"""Prix des carburants des stations suivies dans Home Assistant (intégration « Prix Carburant »,
Aohzan/hass-prixcarburant), lus par l'API REST de Home Assistant.

Chaque carburant d'une station est une entité sensor (prix en €/l) avec les attributs
station_id, fuel_type, shortage_since (rupture en cours), updated_date… L'adresse de Home
Assistant et le jeton d'accès longue durée restent sur ce PC (home_assistant.json, dossier des
données) ; le jeton n'est envoyé qu'à cette adresse."""
import json
import ssl
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from . import config

HA_FILE = "home_assistant.json"   # {"url": "https://…", "token": "…"}
REFRESH = 300                     # s entre deux lectures (l'intégration se met à jour ~4 h)
RETRY = 60
FUEL_ORDER = ("Gazole", "E10", "SP95", "SP98", "E85", "GPLc")
OFF_STATES = ("unavailable", "unknown", "none", "")


def load_ha():
    data = config.load(HA_FILE, {}) or {}
    return (data.get("url") or "").strip().rstrip("/"), (data.get("token") or "").strip()


def save_ha(url, token):
    config.save(HA_FILE, {"url": url.strip().rstrip("/"), "token": token.strip()})


def configured():
    url, token = load_ha()
    return bool(url and token)


def fetch_states(url, token):
    """Tous les états de Home Assistant (GET /api/states)."""
    # User-Agent explicite : Cloudflare (ou un autre proxy devant Home Assistant) refuse celui
    # de Python par défaut (« Python-urllib », erreur 1010) avant même Home Assistant
    req = urllib.request.Request(f"{url}/api/states", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json",
        "User-Agent": "G19Monitor/1.0 (+https://github.com/fauwzk/g19-monitor)"})
    with urllib.request.urlopen(req, timeout=15, context=ssl.create_default_context()) as r:
        return json.loads(r.read().decode("utf-8"))


def http_error_text(e):
    """Message court pour une erreur HTTP de la lecture des états."""
    if e.code == 401:
        return "jeton refusé par Home Assistant"
    if e.code == 403:
        try:
            body = e.read(300).decode("utf-8", "replace")
        except Exception:
            body = ""
        if "cloudflare" in (e.headers.get("server") or "").lower() or "error code" in body:
            return "accès bloqué par Cloudflare (règle de pare-feu)"
        return "accès refusé (403) : jeton sans droits ou proxy"
    return f"Home Assistant : erreur {e.code}"


def short_name(name):
    """« Station Intermarché JOINVILLE » → « Intermarché JOINVILLE »."""
    for prefix in ("Station ", "Relais "):
        if name.startswith(prefix) and len(name) > len(prefix) + 2:
            return name[len(prefix):]
    return name


def _age_days(updated):
    try:
        dt = datetime.strptime(updated, "%Y-%m-%dT%H:%M:%S%z")
    except (TypeError, ValueError):
        return None
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400)


def parse_states(states):
    """États Home Assistant → {station_id: {"name", "short", "city", "brand",
    "fuels": {carburant: {"price", "out", "shortage", "updated", "age"}}}}."""
    stations = {}
    for st in states or ():
        a = st.get("attributes") or {}
        sid, fuel = a.get("station_id"), a.get("fuel_type")
        if not sid or not fuel or not str(st.get("entity_id", "")).startswith("sensor."):
            continue
        friendly = (a.get("friendly_name") or "").strip()
        name = friendly[:-len(fuel)].strip() if friendly.endswith(fuel) else \
            (a.get("name") or a.get("brand") or str(sid))
        s = stations.setdefault(str(sid), {"name": name, "short": short_name(name),
                                           "city": a.get("city") or "",
                                           "brand": a.get("brand") or "", "fuels": {}})
        state = str(st.get("state", "")).strip().lower()
        try:
            price = float(state) if state not in OFF_STATES else None
        except ValueError:
            price = None
        shortage = a.get("shortage_since")
        s["fuels"][fuel] = {"price": price, "shortage": shortage,
                            # plus disponible : rupture déclarée, ou plus de prix du tout
                            "out": bool(shortage) or price is None,
                            "updated": a.get("updated_date"),
                            "age": _age_days(a.get("updated_date"))}
    return dict(sorted(stations.items(), key=lambda kv: kv[1]["short"].casefold()))


def fuels_of(stations):
    """Carburants vendus par au moins une station, dans l'ordre habituel."""
    seen = {f for s in stations.values() for f in s["fuels"]}
    return [f for f in FUEL_ORDER if f in seen] + sorted(seen - set(FUEL_ORDER))


def cheapest(stations, fuel):
    """(prix, station) le moins cher pour `fuel` parmi les stations qui en ont, ou None."""
    best = None
    for s in stations.values():
        f = s["fuels"].get(fuel)
        if f and not f["out"] and f["price"] is not None:
            if best is None or f["price"] < best[0]:
                best = (f["price"], s)
    return best


def changes(before, after):
    """[(station, carburant, en rupture ?, prix)] des carburants passés en rupture ou revenus."""
    out = []
    for sid, s in after.items():
        old = before.get(sid)
        if not old:
            continue
        for fuel, f in s["fuels"].items():
            o = old["fuels"].get(fuel)
            if o and o["out"] != f["out"]:
                out.append((s, fuel, f["out"], f["price"]))
    return out


def change_event(diffs, now):
    """Bandeau (titre, texte, horodatage) pour les changements d'un passage."""
    if not diffs:
        return None
    parts = []
    for s, fuel, out, price in diffs:
        txt = f"{fuel} en rupture" if out else f"{fuel} de retour" + \
            (f" · {fmt_price(price)} €" if price is not None else "")
        parts.append(txt if len({d[0]["short"] for d in diffs}) == 1 else f"{s['short']} : {txt}")
    stations = {d[0]["short"] for d in diffs}
    title = f"Carburant · {next(iter(stations))}" if len(stations) == 1 else "Carburant"
    return title, " · ".join(parts), now


def fmt_price(p):
    return f"{p:.3f}".replace(".", ",")


class FuelMonitor:
    def __init__(self):
        self.stations = {}
        self.status = "lecture…"   # "" : à jour
        self.updated_at = 0.0      # dernière lecture réussie
        self.event = None          # (titre, texte, horodatage) : rupture / retour
        self._wake = threading.Event()
        threading.Thread(target=self._run, daemon=True, name="carburant").start()

    def check_now(self):
        self._wake.set()

    def _run(self):
        while True:
            wait = REFRESH
            try:
                url, token = load_ha()
                if not (url and token):
                    self.status, wait = "Home Assistant non configuré", 30
                else:
                    data = parse_states(fetch_states(url, token))
                    if not data:
                        self.status = "aucune station Prix Carburant dans Home Assistant"
                    else:
                        if self.stations:
                            ev = change_event(changes(self.stations, data), time.time())
                            if ev:
                                self.event = ev
                        self.status = ""
                    self.stations, self.updated_at = data, time.time()
            except urllib.error.HTTPError as e:
                self.status = http_error_text(e)
                wait = RETRY
            except Exception:
                self.status, wait = "Home Assistant injoignable", RETRY
            if self._wake.wait(wait):
                self._wake.clear()
