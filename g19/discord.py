"""Client Discord RPC local (pipe \\\\.\\pipe\\discord-ipc-N) : salon vocal, qui parle, muet,
notifications de messages.

Nécessite une application Discord à toi (client id/secret) autorisée une fois avec
setup_discord.py ; les jetons sont gardés dans %LOCALAPPDATA%\\G19Monitor\\discord.json.
"""
import ctypes
import io
import json
import re
import msvcrt
import queue
import struct
import threading
import time
import urllib.parse
import urllib.request
import uuid
from collections import deque
from ctypes import wintypes

from PIL import Image, ImageDraw, ImageOps

import psutil

from . import config

DISCORD_EXES = {"discord.exe", "discordptb.exe", "discordcanary.exe"}


def discord_running():
    """L'appli Discord (stable, PTB ou Canary) est-elle ouverte ?"""
    return any((p.info["name"] or "").lower() in DISCORD_EXES
               for p in psutil.process_iter(["name"]))

CONFIG_FILE = "discord.json"
SCOPES = ["rpc", "rpc.voice.read", "rpc.voice.write", "rpc.notifications.read", "identify"]
REDIRECT_URI = "http://localhost"
TOKEN_URL = "https://discord.com/api/oauth2/token"
UA = {"User-Agent": "G19Monitor (local, 1.0)"}

OP_HANDSHAKE, OP_FRAME, OP_CLOSE, OP_PING, OP_PONG = range(5)

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.PeekNamedPipe.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                               wintypes.LPVOID, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
_k32.PeekNamedPipe.restype = wintypes.BOOL


class RpcError(Exception):
    pass


class Pipe:
    """Connexion IPC brute. Les lectures passent par PeekNamedPipe pour ne jamais bloquer :
    sur un handle synchrone, une lecture en attente bloquerait aussi les écritures."""

    def __init__(self):
        for i in range(10):
            try:
                self.f = open(rf"\\.\pipe\discord-ipc-{i}", "r+b", buffering=0)
                break
            except OSError:
                continue
        else:
            raise RpcError("Discord n'est pas lancé")
        self.handle = msvcrt.get_osfhandle(self.f.fileno())

    def send(self, op, payload):
        data = json.dumps(payload).encode()
        self.f.write(struct.pack("<II", op, len(data)) + data)

    def available(self):
        n = wintypes.DWORD(0)
        if not _k32.PeekNamedPipe(self.handle, None, 0, None, ctypes.byref(n), None):
            raise RpcError("connexion Discord perdue")
        return n.value

    def _read(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.f.read(n - len(buf))
            if not chunk:
                raise RpcError("connexion Discord perdue")
            buf += chunk
        return buf

    def recv(self, timeout=None):
        """Un message (op, dict), ou None si rien n'arrive avant `timeout`."""
        end = time.time() + (timeout or 0)
        while self.available() < 8:
            if timeout is None or time.time() >= end:
                return None
            time.sleep(0.02)
        op, length = struct.unpack("<II", self._read(8))
        return op, json.loads(self._read(length))

    def command(self, cmd, args=None, evt=None):
        nonce = str(uuid.uuid4())
        msg = {"cmd": cmd, "args": args or {}, "nonce": nonce}
        if evt:
            msg["evt"] = evt
        self.send(OP_FRAME, msg)
        return nonce

    def call(self, cmd, args=None, timeout=120):
        """Commande synchrone (utilisée par setup_discord.py)."""
        nonce = self.command(cmd, args)
        end = time.time() + timeout
        while time.time() < end:
            msg = self.recv(timeout=0.5)
            if msg and msg[1].get("nonce") == nonce:
                if msg[1].get("evt") == "ERROR":
                    raise RpcError(msg[1]["data"].get("message", "erreur"))
                return msg[1].get("data")
        raise RpcError(f"pas de réponse à {cmd}")

    def handshake(self, client_id):
        self.send(OP_HANDSHAKE, {"v": 1, "client_id": str(client_id)})
        msg = self.recv(timeout=10)
        if not msg:
            raise RpcError("pas de réponse de Discord")
        op, data = msg
        if op == OP_CLOSE or data.get("evt") == "ERROR":
            raise RpcError(data.get("message") or data.get("data", {}).get("message", "refusé"))
        return data.get("data", {}).get("user")

    def close(self):
        try:
            self.f.close()
        except OSError:
            pass


def exchange_token(cfg, **params):
    """Échange un code d'autorisation ou un refresh token contre des jetons, et les enregistre."""
    body = urllib.parse.urlencode({"client_id": cfg["client_id"],
                                   "client_secret": cfg["client_secret"], **params}).encode()
    req = urllib.request.Request(TOKEN_URL, body, {
        **UA, "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=15) as r:
        tok = json.loads(r.read())
    cfg.update(access_token=tok["access_token"], refresh_token=tok.get("refresh_token"),
               expires_at=time.time() + tok.get("expires_in", 604800))
    config.save(CONFIG_FILE, cfg)
    return cfg


def authorize(client_id, client_secret):
    """Demande l'autorisation dans Discord (fenêtre à accepter) et enregistre les jetons.
    Renvoie le nom du compte Discord."""
    cfg = config.load(CONFIG_FILE, {}) or {}
    cfg.update(client_id=client_id.strip(), client_secret=client_secret.strip())
    pipe = Pipe()
    try:
        user = pipe.handshake(cfg["client_id"])
        code = pipe.call("AUTHORIZE", {"client_id": cfg["client_id"], "scopes": SCOPES})["code"]
    finally:
        pipe.close()
    exchange_token(cfg, grant_type="authorization_code", code=code, redirect_uri=REDIRECT_URI)
    return (user or {}).get("global_name") or (user or {}).get("username", "?")


def forget():
    cfg = config.load(CONFIG_FILE, {}) or {}
    for k in ("access_token", "refresh_token", "expires_at"):
        cfg.pop(k, None)
    config.save(CONFIG_FILE, cfg)


def avatar_url(user):
    if not user:
        return None
    if user.get("avatar"):
        return f"https://cdn.discordapp.com/avatars/{user['id']}/{user['avatar']}.png?size=64"
    return f"https://cdn.discordapp.com/embed/avatars/{(int(user.get('id', 0)) >> 22) % 6}.png"


class AvatarCache:
    """Avatars ronds téléchargés en tâche de fond."""

    def __init__(self):
        self._img = {}
        self._q = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def get(self, url, size):
        if not url:
            return None
        key = (url, size)
        if key not in self._img:
            self._img[key] = None
            self._q.put(key)
        return self._img[key]

    def _run(self):
        while True:
            url, size = self._q.get()
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=10) as r:
                    img = Image.open(io.BytesIO(r.read())).convert("RGB")
                img = ImageOps.fit(img, (size, size), Image.LANCZOS)
                mask = Image.new("L", (size * 4, size * 4), 0)
                ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
                img.putalpha(mask.resize((size, size), Image.LANCZOS))
                self._img[(url, size)] = img
            except Exception:
                pass


class DiscordClient:
    def __init__(self):
        self.status = "init"      # non configuré / fermé / connecté / erreur…
        self.user = None
        self.voice = None         # {id, name, guild, members: {uid: {...}}}
        self.self_mute = self.self_deaf = False
        self.notifications = deque(maxlen=20)
        self.unread = 0
        self.last_notification = 0.0
        self.voice_event = None   # (nom, texte, avatar, horodatage) : arrivée / départ dans l'appel
        self.avatars = AvatarCache()
        self._out = queue.Queue()
        self._pipe = None
        self._guilds = {}
        self._channels = {}       # id → {"name", "type", "guild_id"} (lieu des messages)
        threading.Thread(target=self._run, daemon=True).start()

    # --- actions depuis l'affichage ---

    def toggle_mute(self):
        self._out.put(("SET_VOICE_SETTINGS", {"mute": not self.self_mute}))

    def toggle_deaf(self):
        self._out.put(("SET_VOICE_SETTINGS", {"deaf": not self.self_deaf}))

    def mark_read(self):
        self.unread = 0

    # --- boucle de connexion ---

    def _run(self):
        while True:
            cfg = config.load(CONFIG_FILE, {})
            if not cfg.get("client_id") or not cfg.get("access_token"):
                self.status = "non configuré"
                time.sleep(15)
                continue
            try:
                self._session(cfg)
            except RpcError as e:
                self.status = str(e)
            except Exception as e:  # réseau, JSON inattendu…
                self.status = f"erreur : {e}"
            finally:
                if self._pipe:
                    self._pipe.close()
                    self._pipe = None
                self.voice = None
            time.sleep(10)

    def _session(self, cfg):
        if cfg.get("expires_at", 0) - time.time() < 86400 and cfg.get("refresh_token"):
            cfg = exchange_token(cfg, grant_type="refresh_token", refresh_token=cfg["refresh_token"])
        pipe = self._pipe = Pipe()
        pipe.handshake(cfg["client_id"])
        auth = pipe.command("AUTHENTICATE", {"access_token": cfg["access_token"]})
        self.status = "connexion…"
        while True:
            while not self._out.empty():
                cmd, args = self._out.get()
                pipe.command(cmd, args)
            msg = pipe.recv(timeout=0.1)
            if not msg:
                continue
            op, data = msg
            if op == OP_CLOSE:
                raise RpcError(data.get("message", "Discord a fermé la connexion"))
            if op == OP_PING:
                pipe.send(OP_PONG, data)
                continue
            if data.get("nonce") == auth:
                if data.get("evt") == "ERROR":
                    # jeton refusé : on tente un rafraîchissement au prochain essai
                    cfg["expires_at"] = 0
                    config.save(CONFIG_FILE, cfg)
                    raise RpcError("jeton Discord refusé")
                self._on_ready(data["data"])
                continue
            self._handle(data)

    def _on_ready(self, data):
        self.user = data.get("user")
        self.status = "connecté"
        p = self._pipe
        for evt in ("VOICE_CHANNEL_SELECT", "VOICE_SETTINGS_UPDATE", "NOTIFICATION_CREATE"):
            p.command("SUBSCRIBE", evt=evt)
        p.command("GET_SELECTED_VOICE_CHANNEL")
        p.command("GET_VOICE_SETTINGS")

    def _channel_events(self, action, channel_id):
        for evt in ("VOICE_STATE_CREATE", "VOICE_STATE_UPDATE", "VOICE_STATE_DELETE",
                    "SPEAKING_START", "SPEAKING_STOP"):
            self._pipe.command(action, {"channel_id": channel_id}, evt=evt)

    def _handle(self, msg):
        cmd, evt, data = msg.get("cmd"), msg.get("evt"), msg.get("data") or {}
        if evt == "ERROR":
            return
        if cmd == "GET_SELECTED_VOICE_CHANNEL":
            self._set_channel(msg.get("data"))
        elif cmd == "GET_CHANNEL" and data.get("id"):
            self._channels[data["id"]] = {"name": data.get("name") or "",
                                          "type": data.get("type"),
                                          "guild_id": data.get("guild_id")}
            gid = data.get("guild_id")
            if gid and gid not in self._guilds:
                self._pipe.command("GET_GUILD", {"guild_id": gid})
            self._fill_where()
        elif cmd == "GET_GUILD" and data.get("id"):
            self._guilds[data["id"]] = data.get("name", "")
            self._fill_where()
            if self.voice and self.voice.get("guild_id") == data["id"]:
                self.voice["guild"] = data.get("name", "")
        elif cmd in ("GET_VOICE_SETTINGS", "SET_VOICE_SETTINGS") or evt == "VOICE_SETTINGS_UPDATE":
            self.self_mute = bool(data.get("mute"))
            self.self_deaf = bool(data.get("deaf"))
        elif evt == "VOICE_CHANNEL_SELECT":
            if data.get("channel_id"):
                self._pipe.command("GET_SELECTED_VOICE_CHANNEL")
            else:
                self._set_channel(None)
        elif evt in ("VOICE_STATE_CREATE", "VOICE_STATE_UPDATE") and self.voice:
            uid = (data.get("user") or {}).get("id")
            new = uid and uid not in self.voice["members"]
            self._upsert(data)
            m = self.voice["members"].get(uid)
            if evt == "VOICE_STATE_CREATE" and new and m and not m["me"]:
                self.voice_event = (m["name"], f"a rejoint {self.voice['name']}", m["avatar"],
                                    time.time())
        elif evt == "VOICE_STATE_DELETE" and self.voice:
            m = self.voice["members"].pop((data.get("user") or {}).get("id"), None)
            if m and not m["me"]:
                self.voice_event = (m["name"], f"a quitté {self.voice['name']}", m["avatar"],
                                    time.time())
        elif evt in ("SPEAKING_START", "SPEAKING_STOP") and self.voice:
            m = self.voice["members"].get(data.get("user_id"))
            if m:
                m["speaking"] = evt == "SPEAKING_START"
        elif evt == "NOTIFICATION_CREATE":
            message = data.get("message") or {}
            author = message.get("author") or {}
            cid = data.get("channel_id") or message.get("channel_id")
            if cid and cid not in self._channels:
                self._pipe.command("GET_CHANNEL", {"channel_id": cid})   # nom du groupe
            self.notifications.appendleft({
                "channel_id": cid,
                "where": self.where(cid, data.get("title", "")),
                "author": author.get("global_name") or author.get("username") or data.get("title", ""),
                "title": data.get("title", ""),
                "body": data.get("body") or message.get("content", ""),
                "icon": data.get("icon_url") or avatar_url(author),
                "time": time.time(),
            })
            self.unread += 1
            self.last_notification = time.time()

    def where(self, cid, title=""):
        """Lieu d'un message : « Les potes » (groupe), « #général · Serveur », "" en privé.
        Tant que Discord n'a pas répondu : ce que le titre de la notification indique."""
        ch = self._channels.get(cid)
        if ch:
            if ch["type"] == 1:                       # message privé : pas de lieu
                return ""
            if ch["type"] == 3:                       # groupe privé (nom choisi, sinon générique)
                return ch["name"] or "groupe privé"
            guild = self._guilds.get(ch["guild_id"], "")
            name = f"#{ch['name']}" if ch["name"] else ""
            return " · ".join(p for p in (name, guild) if p)
        m = re.search(r"\((.*)\)\s*$", title or "")
        return m.group(1) if m else ""

    def _fill_where(self):
        """Complète le lieu des messages déjà reçus quand Discord répond."""
        for n in self.notifications:
            if n.get("channel_id") in self._channels:
                n["where"] = self.where(n["channel_id"], n.get("title", ""))

    def _set_channel(self, ch):
        old = self.voice
        if old and (not ch or ch.get("id") != old["id"]):
            self._channel_events("UNSUBSCRIBE", old["id"])
        if not ch:
            self.voice = None
            return
        guild_id = ch.get("guild_id")
        self.voice = {"id": ch["id"], "name": ch.get("name") or "Appel privé",
                      "guild_id": guild_id, "guild": self._guilds.get(guild_id, ""),
                      "members": {}}
        for vs in ch.get("voice_states", []):
            self._upsert(vs)
        if not old or old["id"] != ch["id"]:
            self._channel_events("SUBSCRIBE", ch["id"])
        if guild_id and guild_id not in self._guilds:
            self._pipe.command("GET_GUILD", {"guild_id": guild_id})

    def _upsert(self, vs):
        user = vs.get("user") or {}
        uid = user.get("id")
        if not uid:
            return
        st = vs.get("voice_state") or {}
        prev = self.voice["members"].get(uid, {})
        self.voice["members"][uid] = {
            "id": uid,
            "name": vs.get("nick") or user.get("global_name") or user.get("username", "?"),
            "avatar": avatar_url(user),
            "mute": bool(st.get("self_mute") or st.get("mute") or vs.get("mute")),
            "deaf": bool(st.get("self_deaf") or st.get("deaf")),
            "speaking": prev.get("speaking", False),
            "me": self.user and uid == self.user.get("id"),
        }
