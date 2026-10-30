"""Écran Audio : lignes réglables (profils, sortie, entrée, volume général, micro, applis) et
touches.

Hors réglage, ▲ ▼ montent / baissent le volume général et OK entre en réglage (sur la ligne des
profils s'il y en a). En réglage, ▲ ▼ choisissent la ligne, ◄ ► règlent (ou parcourent les
périphériques ; sur les profils : passent aussitôt au précédent / suivant), OK coupe le son,
applique le périphérique choisi ou passe au profil suivant, Annuler / Menu sortent."""
from .volume import STEP


def profiles(c):
    return [p for p in (c.settings or {}).get("audio_profiles") or () if p.get("name")]


def next_profile(c, step=1):
    """Profil après (ou avant) celui en cours ; le premier si aucun ne correspond."""
    profs = profiles(c)
    if not profs:
        return None
    cur = c.volume.active_profile(profs) if c.volume else None
    if cur is None:
        return profs[0] if step > 0 else profs[-1]
    return profs[(cur + step) % len(profs)]


def rows(vol, profs=()):
    """Lignes de l'écran, dans l'ordre : [{"kind", ...}]."""
    if not vol:
        return []
    out = [{"kind": "profile"}] if profs else []
    out += [{"kind": "out"}, {"kind": "in"}, {"kind": "master"}]
    if vol.mic_level is not None:
        out.append({"kind": "mic"})
    out += [{"kind": "app", "key": s["key"]} for s in vol.sessions]
    return out


def devices(vol, kind):
    return (vol.outputs, vol.out_id) if kind == "out" else (vol.inputs, vol.in_id)


def picked(c, kind):
    """Indice du périphérique affiché pour la ligne `kind` (choix en cours, sinon l'actuel)."""
    devs, current = devices(c.volume, kind)
    if kind in c.audio_pick:
        return c.audio_pick[kind] % max(1, len(devs))
    ids = [d[0] for d in devs]
    return ids.index(current) if current in ids else 0


def handle(c, b):
    """Traite une touche sur l'écran Audio ; True si elle a été consommée."""
    vol = c.volume
    if not vol:
        return False
    profs = profiles(c)
    if c.audio_cursor is None:
        if b == "ok":
            # curseur sur les profils s'il y en a (OK, OK : profil suivant), sinon sur le volume
            c.audio_cursor, c.audio_pick = (0 if profs else 2), {}
            return True
        if b in ("up", "down"):
            vol.do("master", STEP if b == "up" else -STEP)
            return True
        return False
    lines = rows(vol, profs)
    if not lines:
        c.audio_cursor = None
        return True
    i = c.audio_cursor = min(c.audio_cursor, len(lines) - 1)
    row = lines[i]
    kind = row["kind"]
    if b in ("cancel", "menu"):
        c.audio_cursor, c.audio_pick = None, {}
    elif b in ("up", "down"):
        c.audio_cursor = (i + (1 if b == "down" else -1)) % len(lines)
        c.audio_pick = {}
    elif kind == "profile" and b in ("left", "right", "ok"):
        p = next_profile(c, -1 if b == "left" else 1)
        if p:
            vol.do("profile", p)
    elif b in ("left", "right"):
        step = 1 if b == "right" else -1
        if kind in ("out", "in"):
            devs, _ = devices(vol, kind)
            if devs:
                c.audio_pick = {kind: (picked(c, kind) + step) % len(devs)}
        elif kind == "app":
            vol.do("app", row["key"], STEP * step)
        else:
            vol.do(kind, STEP * step)
    elif b == "ok":
        if kind in ("out", "in"):
            devs, current = devices(vol, kind)
            if devs:
                dev_id = devs[picked(c, kind)][0]
                if dev_id != current:
                    vol.do("default", dev_id)
            c.audio_pick = {}
        elif kind == "app":
            vol.do("app_mute", row["key"])
        else:
            vol.do(kind + "_mute")
    return True
