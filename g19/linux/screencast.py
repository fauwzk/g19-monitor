"""Recopie de l'écran du PC sous Linux (Wayland comme X11) : portail xdg-desktop-portal
ScreenCast, puis le flux PipeWire lu par GStreamer et réduit pour le G19. La première fois,
le bureau demande quel écran partager ; le choix est mémorisé (jeton de restauration), la
capture reprend ensuite sans redemander. Même interface que screencap.ScreenMirror.

Le portail parle par signaux D-Bus : ce fil a sa propre boucle GLib (contexte à lui), pour ne
pas gêner celle de l'icône de la barre des tâches."""
import threading
import time

from .. import config

SIZE = (320, 214)          # sous la barre du haut
ZOOMS = (1, 2, 4)
STREAM_W = 960             # largeur du flux : de quoi zoomer ×2 / ×4 sans flou excessif
TOKEN_FILE = "screencast.json"
IDLE_STOP = 5.0            # s sans la page à l'écran : flux en pause
PORTAL = "org.freedesktop.portal.Desktop"
PATH = "/org/freedesktop/portal/desktop"
IFACE = "org.freedesktop.portal.ScreenCast"


class LinuxMirror:
    def __init__(self):
        self.frame = None
        self.cursor = None         # curseur incrusté dans l'image par le bureau
        self.screen = 0
        self.count = 1
        self.zoom = 0
        self.label = ""
        self.status = "en attente de la page…"
        self.fps = 0.0
        self._wanted = 0.0
        self._restart = threading.Event()
        threading.Thread(target=self._run, daemon=True, name="recopie d'écran").start()

    def want(self):
        self._wanted = time.time()

    def next_screen(self):
        """OK : choisir un autre écran (le bureau redemande lequel)."""
        config.save(TOKEN_FILE, {})
        self._restart.set()

    def zoom_in(self, step):
        self.zoom = max(0, min(len(ZOOMS) - 1, self.zoom + step))

    # --- portail ---

    def _portal_session(self, Gio, GLib, ctx):
        conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        sender = conn.get_unique_name()[1:].replace(".", "_")
        counter = [0]

        def request(method, *args):
            """Appel du portail qui répond par un signal Response : (code, résultats)."""
            counter[0] += 1
            token = f"g19_{counter[0]}_{int(time.time())}"
            path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
            box = {}

            def on_response(_c, _s, _p, _i, _sig, params):
                box["r"] = params.unpack()

            sub = conn.signal_subscribe(PORTAL, "org.freedesktop.portal.Request", "Response",
                                        path, None, Gio.DBusSignalFlags.NO_MATCH_RULE,
                                        on_response)
            *head, options = args
            options = dict(options, handle_token=GLib.Variant("s", token))
            params = GLib.Variant(f"({''.join(a[0] for a in head)}a{{sv}})",
                                  (*[a[1] for a in head], options))
            conn.call_sync(PORTAL, PATH, IFACE, method, params, None,
                           Gio.DBusCallFlags.NONE, -1, None)
            end = time.time() + 300           # le temps de répondre à la demande du bureau
            while "r" not in box and time.time() < end:
                ctx.iteration(True)
            conn.signal_unsubscribe(sub)
            if "r" not in box:
                raise TimeoutError("pas de réponse du portail")
            return box["r"]

        code, res = request("CreateSession", {"session_handle_token":
                                              GLib.Variant("s", f"g19s{int(time.time())}")})
        if code:
            raise PermissionError("session refusée")
        session = res["session_handle"]
        saved = (config.load(TOKEN_FILE, {}) or {}).get("restore_token")
        opts = {"types": GLib.Variant("u", 1), "multiple": GLib.Variant("b", False),
                "cursor_mode": GLib.Variant("u", 2), "persist_mode": GLib.Variant("u", 2)}
        if saved:
            opts["restore_token"] = GLib.Variant("s", saved)
        self.status = "choisis l'écran à partager sur le PC…"
        code, _ = request("SelectSources", ("o", session), opts)
        if code:
            raise PermissionError("partage refusé")
        code, res = request("Start", ("o", session), ("s", ""), {})
        if code:
            raise PermissionError("partage refusé sur le PC")
        if res.get("restore_token"):
            config.save(TOKEN_FILE, {"restore_token": res["restore_token"]})
        streams = res.get("streams") or []
        if not streams:
            raise OSError("aucun écran partagé")
        node, props = streams[0]
        result, fds = conn.call_with_unix_fd_list_sync(
            PORTAL, PATH, IFACE, "OpenPipeWireRemote",
            GLib.Variant("(oa{sv})", (session, {})), None, Gio.DBusCallFlags.NONE, -1, None,
            None)
        fd = fds.get(result.unpack()[0])
        size = props.get("size")
        return conn, session, node, fd, size

    # --- flux ---

    def _run(self):
        try:
            import gi
            gi.require_version("Gst", "1.0")
            from gi.repository import Gio, GLib, Gst
            Gst.init(None)
        except (ImportError, ValueError) as e:
            self.status = f"GStreamer indisponible ({e.__class__.__name__})"
            return
        while True:
            while time.time() - self._wanted > 1.0:     # page pas à l'écran : on attend
                time.sleep(0.3)
            ctx = GLib.MainContext()
            ctx.push_thread_default()
            pipe = None
            try:
                self.status = "connexion au portail…"
                conn, session, node, fd, size = self._portal_session(Gio, GLib, ctx)
                # hauteur imposée (proportions de l'écran) : laissée libre, GStreamer prend 1 px
                sw, sh = (size if size and size[0] else (16, 9))
                height = max(2, round(STREAM_W * sh / sw / 2) * 2)
                pipe = Gst.parse_launch(
                    f"pipewiresrc fd={fd} path={node} always-copy=true do-timestamp=true ! "
                    f"videoconvert ! videoscale ! video/x-raw,format=RGB,width={STREAM_W},"
                    f"height={height},pixel-aspect-ratio=1/1 ! appsink name=sink "
                    f"max-buffers=1 drop=true sync=false")
                sink = pipe.get_by_name("sink")
                pipe.set_state(Gst.State.PLAYING)
                self.status = ""
                self.label = f"écran partagé · {size[0]}×{size[1]}" if size else "écran partagé"
                self._stream(Gst, pipe, sink)
            except Exception as e:
                self.status = f"recopie impossible : {e}"[:80]
                time.sleep(3)
            finally:
                if pipe is not None:
                    pipe.set_state(Gst.State.NULL)
                ctx.pop_thread_default()
            self._restart.clear()

    def _stream(self, Gst, pipe, sink):
        from PIL import Image
        frames, fps_at, paused = 0, time.time(), False
        while not self._restart.is_set():
            now = time.time()
            idle = now - self._wanted > IDLE_STOP
            if idle != paused:                 # page quittée : flux en pause, puis reprise
                pipe.set_state(Gst.State.PAUSED if idle else Gst.State.PLAYING)
                paused = idle
            if paused:
                time.sleep(0.2)
                continue
            sample = sink.emit("try-pull-sample", int(0.5 * Gst.SECOND))
            if sample is None:
                continue
            caps = sample.get_caps().get_structure(0)
            w, h = caps.get_value("width"), caps.get_value("height")
            buf = sample.get_buffer()
            ok, info = buf.map(Gst.MapFlags.READ)
            if not ok:
                continue
            try:
                stride = len(info.data) // h
                img = Image.frombuffer("RGB", (w, h), bytes(info.data), "raw", "RGB", stride, 1)
            finally:
                buf.unmap(info)
            self.frame = self._fit(img)
            frames += 1
            if now - fps_at >= 2:
                self.fps, frames, fps_at = frames / (now - fps_at), 0, now

    def _fit(self, img):
        z = ZOOMS[self.zoom]
        w, h = img.size
        if z > 1:                              # zoom au centre (le curseur n'est pas connu)
            cw, ch = w // z, h // z
            img = img.crop(((w - cw) // 2, (h - ch) // 2, (w + cw) // 2, (h + ch) // 2))
            w, h = img.size
        scale = min(SIZE[0] / w, SIZE[1] / h)
        from PIL import Image
        return img.resize((max(1, round(w * scale)), max(1, round(h * scale))),
                          Image.BILINEAR)
