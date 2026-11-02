"""Home Assistant depuis le clavier : lumières, prises, interrupteurs, scènes et scripts, à
allumer / éteindre / lancer avec OK (page Maison).

Même accès que la page Carburant (home_assistant.json : adresse et jeton). Les appareils
affichés sont ceux choisis dans l'utilitaire (réglage ha_entities) ; sans choix, les lumières
disponibles et les scènes (12 au plus : les intégrations ajoutent souvent des centaines
d'interrupteurs, à choisir à la main)."""
import json
import ssl
import threading
import time
import urllib.error
import urllib.request

from .fuel import http_error_text, load_ha

REFRESH = 5                   # s entre deux lectures, page Maison affichée
REFRESH_IDLE = 60             # s sinon (la lecture de tous les états est lourde)
AUTO_MAX = 12
# domaine → (service d'OK, priorité dans le choix automatique)
DOMAINS = {"light": ("toggle", 0), "switch": ("toggle", 1), "input_boolean": ("toggle", 2),
           "fan": ("toggle", 3), "cover": ("toggle", 4), "scene": ("turn_on", 5),
           "script": ("turn_on", 6)}
UA = "G19Monitor (Logitech G19 LCD applet)"


def _request(url, token, path, body=None):
    # User-Agent explicite : Cloudflare refuse « Python-urllib » (erreur 1010)
    req = urllib.request.Request(f"{url}{path}", data=None if body is None else
                                 json.dumps(body).encode("utf-8"),
                                 method="GET" if body is None else "POST",
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/json",
                                          "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15, context=ssl.create_default_context()) as r:
        return json.loads(r.read().decode("utf-8") or "null")


def controllable(states):
    """États Home Assistant → [{"id", "name", "domain", "state"}] pilotables, triés."""
    out = []
    for st in states or ():
        eid = st.get("entity_id", "")
        domain = eid.split(".", 1)[0]
        if domain not in DOMAINS:
            continue
        a = st.get("attributes") or {}
        out.append({"id": eid, "name": (a.get("friendly_name") or eid).strip(),
                    "domain": domain, "state": st.get("state", ""),
                    "brightness": a.get("brightness")})
    out.sort(key=lambda e: (DOMAINS[e["domain"]][1], e["name"].casefold()))
    return out


def is_on(e):
    return e["state"] in ("on", "open", "opening", "playing")


class Home:
    def __init__(self, chosen=lambda: []):
        self.chosen = chosen             # entity_id choisis dans l'utilitaire
        self.entities = []               # affichées, dans l'ordre
        self.all = []                    # toutes les pilotables (pour l'utilitaire)
        self.status = "lecture…"
        self.event = None                # (titre, texte, horodatage) : action échouée
        self.active = False              # page Maison affichée : lectures plus fréquentes
        self._wake = threading.Event()
        self._lock = threading.Lock()
        threading.Thread(target=self._run, daemon=True, name="maison").start()

    def show(self, active):
        """Page Maison affichée ou non ; à l'arrivée sur la page, relecture tout de suite."""
        if active and not self.active:
            self._wake.set()
        self.active = active

    def configured(self):
        url, token = load_ha()
        return bool(url and token)

    def _pick(self, all_):
        chosen = [c for c in self.chosen() or [] if c]
        if chosen:
            by_id = {e["id"]: e for e in all_}
            return [by_id[c] for c in chosen if c in by_id]
        auto = [e for e in all_ if e["domain"] in ("light", "scene")
                and e["state"] != "unavailable"]
        return auto[:AUTO_MAX]

    def act(self, entity_id):
        """OK sur un appareil : bascule (ou lance une scène / un script), sans bloquer."""
        threading.Thread(target=self._act, args=(entity_id,), daemon=True).start()

    def _act(self, entity_id):
        url, token = load_ha()
        domain = entity_id.split(".", 1)[0]
        service = DOMAINS.get(domain, ("toggle", 9))[0]
        with self._lock:                 # affiché tout de suite, confirmé à la relecture
            for e in self.entities:
                if e["id"] == entity_id and service == "toggle":
                    e["state"] = "off" if is_on(e) else "on"
        try:
            _request(url, token, f"/api/services/{domain}/{service}", {"entity_id": entity_id})
        except Exception as e:
            name = next((x["name"] for x in self.entities if x["id"] == entity_id), entity_id)
            self.event = (f"Maison · {name}", "action refusée : " + (
                http_error_text(e) if isinstance(e, urllib.error.HTTPError) else str(e)),
                time.time())
        time.sleep(0.6)
        self._wake.set()

    def _run(self):
        while True:
            url, token = load_ha()
            if not (url and token):
                self.entities, self.status = [], "Home Assistant non configuré"
            else:
                try:
                    all_ = controllable(_request(url, token, "/api/states"))
                    with self._lock:
                        self.all = all_
                        self.entities = self._pick(all_)
                    self.status = "" if all_ else "aucun appareil pilotable"
                except urllib.error.HTTPError as e:
                    self.status = http_error_text(e)
                except Exception as e:
                    self.status = str(e) or e.__class__.__name__
            if self._wake.wait(REFRESH if self.active else REFRESH_IDLE):
                self._wake.clear()
