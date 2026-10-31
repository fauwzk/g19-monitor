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
            "&minutely_15=precipitation&forecast_minutely_15=8&past_minutely_15=1"
            "&timezone=auto&forecast_days=5&timeformat=unixtime")
RAIN_MM = 0.2             # mm en 15 min : il pleut vraiment
RAIN_AHEAD = 45 * 60      # prévenir jusqu'à 45 min avant
RAIN_QUIET = 3600         # pas de nouveau bandeau tant qu'il a plu (ou prévu) dans l'heure
IP_SERVICES = [
    ("https://ipwho.is/?fields=success,city,region,country,latitude,longitude",
     ("city", "region", "country", "latitude", "longitude")),
    ("https://freeipapi.com/api/json",
     ("cityName", "regionName", "countryName", "latitude", "longitude")),
]
IP_CACHE = 6 * 3600       # la position par IP est redemandée toutes les 6 h
LOC_CACHE = 30 * 60       # position Windows relue toutes les 30 min (PC portable qui bouge)
REVERSE = ("https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=10"
           "&accept-language=fr&lat={lat}&lon={lon}")
REFRESH = 10 * 60
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


def rain_soon(data, now):
    """(minutes avant la pluie, mm sur le premier quart d'heure pluvieux) s'il ne pleut pas
    maintenant mais qu'il va pleuvoir dans les RAIN_AHEAD s ; None sinon."""
    m = (data or {}).get("minutely_15") or {}
    steps = [(t, p or 0.0) for t, p in zip(m.get("time") or [], m.get("precipitation") or [])]
    now_mm = max((p for t, p in steps if t <= now < t + 900), default=0.0)
    if now_mm >= RAIN_MM:
        return None
    for t, p in steps:
        if now < t <= now + RAIN_AHEAD and p >= RAIN_MM:
            return max(5, int(round((t - now) / 300.0)) * 5), p
    return None


def raining_or_soon(data, now):
    m = (data or {}).get("minutely_15") or {}
    return any(t <= now + RAIN_AHEAD and t + 900 > now and (p or 0) >= RAIN_MM
               for t, p in zip(m.get("time") or [], m.get("precipitation") or []))


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


def windows_location(timeout=20):
    """Position donnée par Windows (Wi-Fi, GPS : ~100 m) arrondie à ~1 km, ou None si la
    localisation est coupée (Paramètres → Confidentialité → Localisation) ou indisponible."""
    try:
        import asyncio
        from winrt.windows.devices.geolocation import GeolocationAccessStatus, Geolocator
    except ImportError:
        return None

    async def read():
        if await Geolocator.request_access_async() != GeolocationAccessStatus.ALLOWED:
            return None
        g = Geolocator()
        g.desired_accuracy_in_meters = 500
        pos = await asyncio.wait_for(g.get_geoposition_async(), timeout)
        p = pos.coordinate.point.position
        return round(p.latitude, 2), round(p.longitude, 2)

    try:
        found = asyncio.run(read())
    except Exception:
        return None
    if not found:
        return None
    lat, lon = found
    place = {"name": "?", "admin": "", "country": "", "lat": lat, "lon": lon, "loc": True}
    try:   # nom de la commune (à ~1 km près, la position exacte n'est pas envoyée)
        a = _get(REVERSE.format(lat=lat, lon=lon)).get("address") or {}
        place.update(name=a.get("city") or a.get("town") or a.get("village")
                     or a.get("municipality") or "?", admin=a.get("state", ""),
                     country=a.get("country", ""))
    except Exception:
        pass
    return place


def resolve(city):
    """Lieu de la ville réglée ; sans ville : la position de Windows, sinon d'après l'IP
    (bien moins précis : ville du fournisseur d'accès). Avec cache."""
    cache = config.load("weather_place.json", {}) or {}
    if not city:
        hit = cache.get("__loc__")
        if hit and time.time() - hit.get("at", 0) < LOC_CACHE:
            return hit
        place = windows_location()
        if place:
            place["at"] = time.time()
            cache["__loc__"] = place
            config.save("weather_place.json", cache)
            return place
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
        self.event = None           # (titre, texte, horodatage) : pluie dans peu de temps
        self._rain_seen = 0.0       # dernière fois qu'il pleuvait ou qu'une pluie était prévue
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
                self._check_rain(self.updated)
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

    def _check_rain(self, now):
        soon = rain_soon(self.data, now)
        if soon and now - self._rain_seen > RAIN_QUIET:
            minutes, mm = soon
            where = (self.place or {}).get("name") or ""
            self.event = (f"Pluie dans ~{minutes} min",
                          f"{mm:.1f} mm en 15 min".replace(".", ",") + (f" · {where}" if where
                                                                         else ""), now)
        if soon or raining_or_soon(self.data, now):
            self._rain_seen = now

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
