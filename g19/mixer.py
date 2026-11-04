"""Écran Audio : lignes réglables (profils, sortie, entrée, volume général, micro, applis) et
touches.

Hors réglage, ▲ ▼ montent / baissent le volume général et OK entre en réglage (sur la ligne des
profils s'il y en a). En réglage, ▲ ▼ choisissent la ligne, ◄ ► règlent (ou parcourent les
périphériques ; sur les profils : passent aussitôt au précédent / suivant), OK coupe le son,
applique le périphérique choisi ou passe au profil suivant, Annuler / Menu sortent."""
import os

from .volume import STEP, _find, _headset_score, _speaker_score, auto_profiles


def profiles(c):
    """Profils créés dans l'utilitaire, sinon casque / haut-parleurs détectés tout seuls."""
    own = [p for p in (c.settings or {}).get("audio_profiles") or () if p.get("name")]
    if own and c.volume and os.name != "nt":
        # Linux : profils copiés de Windows (autres périphériques) : gardés seulement si tous
        # trouvent leur sortie, sinon casque / haut-parleurs automatiques
        if not all(_find(c.volume.outputs, p.get("out_id"), p.get("out")) for p in own):
            own = []
    if own or not c.volume:
        return own
    return auto_profiles(c.volume.outputs, c.volume.out_id)


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


# --- bascule automatique casque / haut-parleurs (réglage headset_auto_switch) ---

_seen = {"hyperx": None}


def _pick(profs, want_headset, name=""):
    """Profil casque (de préférence celui de la sortie `name`) ou profil haut-parleurs."""
    profs = [p for p in profs if "débranché" not in (p.get("out") or "")]   # prise vide
    if want_headset:
        cands = [p for p in profs if _headset_score(p.get("out") or "") or
                 "casque" in (p.get("name") or "").casefold()]
        exact = [p for p in cands if name and name.casefold() in (p.get("out") or "").casefold()]
        return (exact or cands or [None])[0]
    cands = [p for p in profs if _speaker_score(p.get("out") or "") or
             "haut-parleur" in (p.get("name") or "").casefold()]
    return (cands or [None])[0]


def auto_switch(c, changes):
    """Casque branché ou allumé → son profil ; retiré ou éteint → les haut-parleurs.
    `changes` : [(nom, "out" | "in", connecté ?)] des sorties apparues / disparues ; le casque
    HyperX sans fil est aussi suivi à son allumage (dongle toujours branché). Renvoie le
    profil appliqué, ou None."""
    hx = getattr(c.batteries, "hyperx", None) if c.batteries else None
    hx_on = bool(hx and hx.connected) if hx is not None else None
    events = [(n, on) for n, flow, on in changes if flow == "out" and _headset_score(n)]
    if hx_on is not None and _seen["hyperx"] is not None and hx_on != _seen["hyperx"]:
        events.append(("hyperx", hx_on))
    _seen["hyperx"] = hx_on
    if not events or not (c.settings or {}).get("headset_auto_switch", True) or not c.volume:
        return None
    name, on = events[-1]
    profs = profiles(c)
    target = _pick(profs, on, name)
    cur = c.volume.active_profile(profs)
    if target is None or (cur is not None and profs[cur] is target):
        return None             # rien à faire, ou déjà sur ce profil
    c.volume.do("profile", target)
    return target
