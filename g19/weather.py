"""Météo via Open-Meteo (gratuit, sans clé) : conditions actuelles, prochaines heures, 5 jours."""
import json
import threading
import time
import urllib.parse
import urllib.request

from . import config

GEOCODE = "https://geocoding-api.open-meteo.com/v1/search?name={}&count=1&language=fr&format=json"
FORECAST = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,"
            "wind_speed_10m,wind_direction_10m,is_day,precipitation"
            "&hourly=temperature_2m,precipitation_probability,weather_code,is_day"
            "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
            "precipitation_probability_max,sunrise,sunset"
            "&timezone=auto&forecast_days=5&timeformat=unixtime")
IP_SERVICES = [
    ("https://ipwho.is/?fields=success,city,region,country,latitude,longitude",
     ("city", "region", "country", "latitude", "longitude")),
    ("https://freeipapi.com/api/json",
     ("cityName", "regionName", "countryName", "latitude", "longitude")),
]
IP_CACHE = 6 * 3600       # la position par IP est redemandée toutes les 6 h
REFRESH = 15 * 60
UA = {"User-Agent": "G19Monitor"}

# code météo WMO → (libellé, famille d'icône)
CODES = {
    0: ("Ciel dégagé", "clear"), 1: ("Peu nuageux", "partly"), 2: ("Partiellement nuageux", "partly"),
    3: ("Couvert", "cloud"), 45: ("Brouillard", "fog"), 48: ("Brouillard givrant", "fog"),
    51: ("Bruine légère", "drizzle"), 53: ("Bruine", "drizzle"), 55: ("Bruine dense", "drizzle"),
    56: ("Bruine verglaçante", "drizzle"), 57: ("Bruine verglaçante", "drizzle"),
    61: ("Pluie faible", "rain"), 63: ("Pluie", "rain"), 65: ("Forte pluie", "rain"),
    66: ("Pluie verglaçante", "rain"), 67: ("Pluie verglaçante", "rain"),
    71: ("Neige faible", "snow"), 73: ("Neige", "snow"), 75: ("Forte neige", "snow"),
    77: ("Grains de neige", "snow"), 80: ("Averses", "rain"), 81: ("Averses", "rain"),
    82: ("Fortes averses", "rain"), 85: ("Averses de neige", "snow"), 86: ("Averses de neige", "snow"),
    95: ("Orage", "storm"), 96: ("Orage et grêle", "storm"), 99: ("Orage et grêle", "storm"),
}


def describe(code):
    return CODES.get(int(code or 0), ("—", "cloud"))


def _get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def geocode(city):
    """{name, admin, country, lat, lon} de la ville, ou None."""
    res = _get(GEOCODE.format(urllib.parse.quote(city))).get("results") or []
    if not res:
        return None
    r = res[0]
    return {"name": r["name"], "admin": r.get("admin1", ""), "country": r.get("country", ""),
            "lat": r["latitude"], "lon": r["longitude"]}


def ip_location():
    """Position approximative d'après l'adresse IP publique (ville du fournisseur d'accès)."""
    for url, (city, region, country, lat, lon) in IP_SERVICES:
        try:
            r = _get(url)
            if r.get("success") is False or r.get(lat) is None:
                continue
            return {"name": r.get(city) or "?", "admin": r.get(region, ""),
                    "country": r.get(country, ""), "lat": r[lat], "lon": r[lon], "ip": True}
        except Exception:
            continue
    return None


def resolve(city):
    """Lieu de la ville réglée, ou d'après l'IP si aucune ville (avec cache)."""
    cache = config.load("weather_place.json", {}) or {}
    if not city:
        hit = cache.get("__ip__")
        if hit and time.time() - hit.get("at", 0) < IP_CACHE:
            return hit
        place = ip_location()
        if not place:
            raise RuntimeError("position introuvable")
        place["at"] = time.time()
    else:
        place = cache.get(city.lower()) or geocode(city)
        if not place:
            raise RuntimeError(f"ville introuvable : {city}")
    cache["__ip__" if not city else city.lower()] = place
    config.save("weather_place.json", cache)
    return place


class WeatherMonitor:
    def __init__(self, get_city):
        self.get_city = get_city        # fonction qui renvoie la ville réglée
        self.place = None
        self.data = None
        self.status = "init"
        self.updated = 0.0
        self._wake = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def refresh(self):
        self._wake.set()

    def _run(self):
        while True:
            city = (self.get_city() or "").strip()   # vide = position d'après l'IP
            try:
                self.place = resolve(city)
                self.data = _get(FORECAST.format(**self.place))
                self.updated = time.time()
                self.status = "ok"
            except Exception as e:
                self.status = str(e) if isinstance(e, RuntimeError) else "hors ligne"
            # réveil anticipé si la ville change
            end = time.time() + (REFRESH if self.status == "ok" else 60)
            while time.time() < end:
                if self._wake.wait(5):
                    self._wake.clear()
                    break
                if (self.get_city() or "").strip() != city:
                    break

    # --- accès pratiques pour l'affichage ---

    def current(self):
        return (self.data or {}).get("current")

    def hours(self, n=8):
        """Les n prochaines heures : [(timestamp, temp, proba pluie, code, jour?)]."""
        h = (self.data or {}).get("hourly")
        if not h:
            return []
        now = time.time() - 1800
        rows = zip(h["time"], h["temperature_2m"], h["precipitation_probability"],
                   h["weather_code"], h["is_day"])
        return [r for r in rows if r[0] >= now][:n]

    def days(self, n=5):
        dd = (self.data or {}).get("daily")
        if not dd:
            return []
        return list(zip(dd["time"], dd["weather_code"], dd["temperature_2m_max"],
                        dd["temperature_2m_min"], dd["precipitation_probability_max"],
                        dd["sunrise"], dd["sunset"]))[:n]


if __name__ == "__main__":
    import sys
    w = WeatherMonitor(lambda: sys.argv[1] if len(sys.argv) > 1 else "Paris")
    for _ in range(30):
        if w.status != "init":
            break
        time.sleep(0.5)
    print(w.status, w.place)
    print(w.current())
    print(w.hours(3))
    print(w.days(2))
