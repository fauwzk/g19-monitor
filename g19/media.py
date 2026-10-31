"""Média en cours (Spotify, navigateur, lecteur Windows…) via les contrôles média système (SMTC)."""
import asyncio
import colorsys
import io
import re
import threading
import time
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from .lcd import W, H

try:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as SessionManager,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
    )
    from winrt.windows.storage.streams import Buffer, InputStreamOptions
except ImportError:  # paquets winrt absents → page média vide
    SessionManager = None

ART = 112
APP_NAMES = {"spotify": "Spotify", "chrome": "Chrome", "msedge": "Edge", "firefox": "Firefox",
             "vlc": "VLC", "zunemusic": "Lecteur multimédia", "deezer": "Deezer",
             "applemusic": "Apple Music", "foobar2000": "foobar2000"}


@dataclass
class MediaState:
    title: str = ""
    artist: str = ""
    album: str = ""
    app: str = ""
    playing: bool = False
    position: float = 0.0     # secondes, à l'instant `stamp`
    duration: float = 0.0
    stamp: float = 0.0
    art: Image.Image | None = field(default=None, repr=False)   # pochette ART×ART arrondie
    bg: Image.Image | None = field(default=None, repr=False)    # fond flouté 320×240
    accent: tuple | None = None                                 # couleur de la pochette (r, g, b)
    estimated: bool = False   # durée inconnue : position comptée par l'appli depuis le début

    def position_at(self, t):
        pos = self.position + (t - self.stamp if self.playing else 0)
        return min(max(pos, 0.0), self.duration) if self.duration else pos


def _app_name(aumid):
    low = aumid.lower()
    for key, name in APP_NAMES.items():
        if key in low:
            return name
    if re.fullmatch(r"[0-9a-f]{16}", low):  # id d'appli web/PWA
        return "Navigateur"
    return re.sub(r"\.exe$", "", aumid.split("!")[-1], flags=re.I)


def _prepare_art(data):
    img = Image.open(io.BytesIO(data)).convert("RGB")
    # les miniatures YouTube sont en 16:9 avec des bandes : on garde le carré central
    w, h = img.size
    if w > h * 1.2:
        img = img.crop(((w - h) // 2, 0, (w + h) // 2, h))
    art = ImageOps.fit(img, (ART, ART), Image.LANCZOS)
    mask = Image.new("L", (ART, ART), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, ART - 1, ART - 1), 10, fill=255)
    art.putalpha(mask)
    return art, _backdrop(img), art_accent(img)


def _backdrop(img):
    """Fond de la page Média : la pochette très floutée, plus colorée, assombrie pour que le
    texte reste lisible, avec une vignette (bords plus sombres) qui donne de la profondeur."""
    bg = ImageOps.fit(img, (W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(22))
    bg = ImageEnhance.Color(bg).enhance(1.35)
    bg = ImageEnhance.Brightness(bg).enhance(0.45)
    vignette = Image.radial_gradient("L").resize((W, H)).point(lambda v: int(255 - v * 0.55))
    return Image.composite(bg, Image.new("RGB", (W, H)), vignette)


def art_accent(img):
    """Couleur marquante de la pochette, en (r, g, b) 0..1 — la luminosité est ajustée à
    l'affichage selon le thème. None pour une pochette sans vraie couleur.

    Palette de la pochette (24 couleurs) ; les nuances d'une même teinte sont regroupées et
    leur surface additionnée, la plus franche du groupe le représente (une moyenne ternirait
    la couleur). Chaque groupe est noté surface × vivacité² : une grande zone terne (beige,
    brun) ne l'emporte pas sur une couleur franche bien présente, et un détail minuscule
    compte peu. Seconde passe plus tolérante pour les pochettes très sombres."""
    small = img.convert("RGB").resize((64, 64), Image.BOX)
    q = small.quantize(colors=24, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    total = 64 * 64
    swatches = []
    for count, idx in q.getcolors():
        r, g, b = (c / 255 for c in pal[idx * 3:idx * 3 + 3])
        h, _s, v = colorsys.rgb_to_hsv(r, g, b)
        swatches.append((h, v, max(r, g, b) - min(r, g, b), count / total, (r, g, b)))
    for min_chroma, min_v in ((0.16, 0.22), (0.12, 0.18)):
        best = _pick_accent([x for x in swatches if x[2] >= min_chroma and x[1] >= min_v])
        if best:
            return best
    return None                 # pochette (presque) en noir et blanc : accent par défaut


def _pick_accent(colorful):
    groups = []
    for x in sorted(colorful, key=lambda x: -x[2]):          # la plus franche d'abord
        for gr in groups:
            dh = abs(x[0] - gr[0][0])
            if min(dh, 1 - dh) < 0.045:                        # même teinte (± 16°)
                gr.append(x)
                break
        else:
            groups.append([x])
    best, best_score = None, 0.0
    for gr in groups:
        area = sum(x[3] for x in gr)
        rep = max(gr, key=lambda x: x[2] * (0.6 + 0.4 * x[3] / area))
        v, chroma = rep[1], rep[2]
        vivid = min(1.0, chroma / 0.6)
        light = 1 - abs(v - 0.75) / 0.75                       # ni trop sombre, ni délavée
        score = area ** 0.5 * vivid ** 2 * (0.6 + 0.4 * light)
        if area < 0.012:
            score *= 0.4                                       # un détail minuscule
        if score > best_score:
            best, best_score = rep[4], score
    return best


class MediaMonitor:
    def __init__(self):
        self.state = None
        self._art_key = None
        self._art = (None, None, None)
        self._session = None
        self._known = None      # dernière frise valide du morceau : (clé, pos, durée, stamp, lecture)
        self._clock = None      # temps de lecture compté nous-mêmes : [clé, cumul, t, lecture]
        if SessionManager is None:
            return
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True).start()
        asyncio.run_coroutine_threadsafe(self._poll(), self._loop)

    async def _poll(self):
        mgr = None
        while True:
            try:
                mgr = mgr or await SessionManager.request_async()
                self.state = await self._snapshot(mgr)
            except Exception:
                self.state, mgr = None, None
            await asyncio.sleep(1)

    async def _snapshot(self, mgr):
        s = self._session = mgr.get_current_session()
        if not s:
            return None
        p = await s.try_get_media_properties_async()
        key = (s.source_app_user_model_id, p.title, p.artist)
        if key != self._art_key:
            self._art_key, self._art = key, (None, None, None)
            if p.thumbnail:
                try:
                    stream = await p.thumbnail.open_read_async()
                    buf = Buffer(stream.size)
                    await stream.read_async(buf, buf.capacity, InputStreamOptions.READ_AHEAD)
                    self._art = _prepare_art(bytes(buf))
                except Exception:
                    pass
        tl = s.get_timeline_properties()
        playing = s.get_playback_info().playback_status == Status.PLAYING
        duration = (tl.end_time - tl.start_time).total_seconds()
        position = (tl.position - tl.start_time).total_seconds()
        now = stamp = time.time()
        if playing and tl.last_updated_time.year > 1601:  # position = dernière mise à jour de l'appli
            stamp = tl.last_updated_time.timestamp()
        if stamp > now:
            stamp = now

        # temps de lecture compté de notre côté, au cas où l'appli ne publie pas sa frise
        ck = self._clock
        if not ck or ck[0] != key:
            ck = self._clock = [key, 0.0, now, playing]
        elif ck[3]:
            ck[1] += now - ck[2]
        ck[2], ck[3] = now, playing

        # Les navigateurs ne publient souvent la frise qu'aux changements d'état (pause…) et
        # la vident parfois en cours de route : on garde la dernière valide du même morceau
        # et on la fait avancer nous-mêmes.
        estimated = False
        kn = self._known
        if duration > 0 and not (playing and position <= 0 and kn and kn[0] == key
                                 and kn[1] > 5):
            self._known = (key, position, duration, stamp, playing)
        elif kn and kn[0] == key:
            position = kn[1] + (now - kn[3] if kn[4] else 0)
            duration, stamp = kn[2], now
            self._known = (key, position, duration, stamp, playing)
        else:
            position, duration, stamp, estimated = ck[1], 0.0, now, True
        return MediaState(title=p.title or "", artist=p.artist or "", album=p.album_title or "",
                          app=_app_name(s.source_app_user_model_id), playing=playing,
                          position=position, duration=max(duration, 0.0), stamp=stamp,
                          art=self._art[0], bg=self._art[1], accent=self._art[2],
                          estimated=estimated)

    def command(self, cmd):
        """'toggle', 'next' ou 'previous' sur la session courante."""
        s = self._session
        if not s:
            return
        call = {"toggle": s.try_toggle_play_pause_async, "next": s.try_skip_next_async,
                "previous": s.try_skip_previous_async}[cmd]

        async def run():
            await call()

        asyncio.run_coroutine_threadsafe(run(), self._loop)
