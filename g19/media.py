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
    bg = ImageOps.fit(img, (W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(18))
    bg = ImageEnhance.Brightness(bg).enhance(0.35)
    return art, bg, art_accent(img)


def art_accent(img):
    """Couleur dominante parmi les couleurs franches de l'image, en (r, g, b) 0..1 — la
    luminosité est ajustée à l'affichage selon le thème. None pour une image sans couleur.

    Les couleurs sont regroupées par famille de teinte (pondérées par surface × intensité) :
    on retient la famille la plus présente, pas un petit détail saturé, et sa couleur moyenne
    plutôt qu'une teinte poussée au maximum."""
    small = img.convert("RGB").resize((48, 48))
    q = small.quantize(colors=24, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    bins = [[0.0, 0.0, 0.0, 0.0, 0] for _ in range(BINS)]   # poids, r, g, b, pixels
    for count, idx in q.getcolors():
        r, g, b = (c / 255 for c in pal[idx * 3:idx * 3 + 3])
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        chroma = max(r, g, b) - min(r, g, b)
        if chroma < 0.12 or l < 0.08 or l > 0.94:   # gris, noir, blanc : pas une couleur
            continue
        w = count * chroma ** 1.5
        k = int(h * BINS) % BINS
        acc = bins[k]
        acc[0] += w
        acc[1] += w * r
        acc[2] += w * g
        acc[3] += w * b
        acc[4] += count
    # une famille de teinte coupée en deux par les cases compte quand même entière
    score = [bins[k][0] + 0.5 * (bins[k - 1][0] + bins[(k + 1) % BINS][0]) for k in range(BINS)]
    k = max(range(BINS), key=score.__getitem__)
    w, r, g, b, pixels = bins[k]
    if not w or pixels < 48 * 48 * 0.02:
        return None             # pochette (presque) en noir et blanc : accent par défaut
    return r / w, g / w, b / w


BINS = 18


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
