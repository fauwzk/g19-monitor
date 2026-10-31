"""Panneau d'appel de la page Discord (▼) : volume de chaque participant (pour moi seul), de mon
micro et de l'appel, quitter l'appel ; dessous, les derniers messages (OK : ouvrir dans Discord).

Touches : ▲ ▼ choisir, ◄ ► régler, OK couper / rétablir (ou ouvrir), Annuler fermer."""
from .launcher import launch

STEP_IN = 5           # micro : 0..100
STEP_OUT = 10         # appel et participants : 0..200 (100 = normal)


def rows(dc):
    """Lignes du panneau : [{"kind", …}] dans l'ordre d'affichage."""
    out = []
    v = dc.voice if dc else None
    if v:
        out.append({"kind": "input"})
        out.append({"kind": "output"})
        others = sorted((m for m in v["members"].values() if not m["me"]),
                        key=lambda m: m["name"].lower())
        out += [{"kind": "member", "id": m["id"]} for m in others]
        out.append({"kind": "leave"})
    for i, n in enumerate(list(dc.notifications) if dc else []):
        out.append({"kind": "message", "index": i})
    return out


def handle(c, b):
    """Touche sur la page Discord ; True si elle a été consommée."""
    dc = c.discord
    if not dc or dc.status != "connecté":
        return False
    if c.discord_cursor is None:
        if b == "down" and rows(dc):
            c.discord_cursor = 0
            return True
        return False
    lines = rows(dc)
    if not lines:
        c.discord_cursor = None
        return True
    i = c.discord_cursor = min(c.discord_cursor, len(lines) - 1)
    row = lines[i]
    kind = row["kind"]
    if b in ("cancel", "menu"):
        c.discord_cursor = None
    elif b in ("up", "down"):
        c.discord_cursor = (i + (1 if b == "down" else -1)) % len(lines)
    elif b in ("left", "right"):
        step = 1 if b == "right" else -1
        if kind == "input" and dc.input_volume is not None:
            dc.set_input_volume(dc.input_volume + STEP_IN * step)
        elif kind == "output" and dc.output_volume is not None:
            dc.set_output_volume(dc.output_volume + STEP_OUT * step)
        elif kind == "member":
            m = dc.voice["members"].get(row["id"]) if dc.voice else None
            if m:
                dc.set_user_volume(row["id"], m.get("volume", 100) + STEP_OUT * step)
    elif b == "ok":
        if kind == "input":
            dc.toggle_mute()
        elif kind == "output":
            dc.toggle_deaf()
        elif kind == "member":
            dc.toggle_user_mute(row["id"])
        elif kind == "leave":
            dc.leave_call()
            c.discord_cursor = None
        elif kind == "message":
            notes = list(dc.notifications)
            n = notes[row["index"]] if row["index"] < len(notes) else None
            url = dc.channel_url(n.get("channel_id")) if n else None
            if url:
                try:
                    launch(url)
                except OSError:
                    pass
    return True
