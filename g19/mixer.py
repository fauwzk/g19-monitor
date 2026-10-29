"""Écran Audio : lignes réglables (sortie, entrée, volume général, micro, applis) et touches.

Hors réglage, ▲ ▼ montent / baissent le volume général et OK entre en réglage. En réglage,
▲ ▼ choisissent la ligne, ◄ ► règlent (ou parcourent les périphériques), OK coupe le son ou
applique le périphérique choisi, Annuler / Menu sortent."""
from .volume import STEP


def rows(vol):
    """Lignes de l'écran, dans l'ordre : [{"kind", ...}]."""
    if not vol:
        return []
    out = [{"kind": "out"}, {"kind": "in"}, {"kind": "master"}]
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
    if c.audio_cursor is None:
        if b == "ok":
            c.audio_cursor, c.audio_pick = 2, {}   # curseur sur le volume général
            return True
        if b in ("up", "down"):
            vol.do("master", STEP if b == "up" else -STEP)
            return True
        return False
    lines = rows(vol)
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
