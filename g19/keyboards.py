"""Claviers Logitech à écran branchés : couleur (G19) ou monochrome (G15, G510, G13).

Lu par l'énumération HID (hidapi, sans droits administrateur) ; le gardien s'en sert pour
lancer l'appli qui correspond à chaque clavier."""
VID = 0x046D

COLOR = {0xC228, 0xC229}                          # G19 / G19s (clavier, écran)
MONO = {0xC222, 0xC221,                           # G15 (1re version)
        0xC226, 0xC227,                           # G15 (2e version)
        0xC22D, 0xC22E,                           # G510 / G510s (sans / avec carte son)
        0xC21C}                                   # G13


def detect():
    """{"color": bool, "mono": bool}, ou None si l'énumération est impossible (hidapi
    absent) : l'appelant fait alors comme avant (l'appli G19 seule)."""
    try:
        import hid
        ids = {d["product_id"] for d in hid.enumerate(VID)}
    except Exception:
        return None
    return {"color": bool(ids & COLOR), "mono": bool(ids & MONO)}


if __name__ == "__main__":
    print(detect())
