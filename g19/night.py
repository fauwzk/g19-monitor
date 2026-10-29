"""Mode nuit : entre deux heures réglables, écran assombri (et thème imposé si choisi),
rétroéclairage discret (seules les alertes clignotent)."""
import time

from PIL import ImageEnhance

HOURS = [f"{h:02d}:00" for h in range(24)] + [f"{h:02d}:30" for h in range(24)]
HOURS.sort()


def _minutes(hhmm, default):
    try:
        h, m = (int(v) for v in str(hhmm).split(":"))
        return (h % 24) * 60 + m % 60
    except ValueError:
        return default


def is_night(cfg, t=None):
    if not cfg.get("night_mode"):
        return False
    lt = time.localtime(t or time.time())
    now = lt.tm_hour * 60 + lt.tm_min
    start = _minutes(cfg.get("night_start"), 23 * 60)
    end = _minutes(cfg.get("night_end"), 7 * 60)
    if start == end:
        return True
    return start <= now < end if start < end else now >= start or now < end


def effective(cfg, night):
    """Réglages réellement appliqués : le thème de nuit remplace le thème la nuit."""
    if night and cfg.get("night_theme"):
        return {**cfg, "theme": cfg["night_theme"]}
    return cfg


def quiet(cfg, night):
    """La nuit, le clavier ne clignote plus que pour les alertes."""
    return night and cfg.get("night_quiet", True)


def dim(img, cfg, night):
    pct = cfg.get("night_dim", 40)
    if not night or pct >= 100:
        return img
    return ImageEnhance.Brightness(img).enhance(max(0.05, pct / 100))
