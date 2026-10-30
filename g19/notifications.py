"""Notifications Windows (toasts de toutes les applis) via UserNotificationListener.

L'accès se règle dans Paramètres → Confidentialité et sécurité → Notifications.
"""
import asyncio
import io
import os
import re
import sqlite3
import threading
import time
from collections import deque

from PIL import Image, ImageOps

try:
    from winrt.windows.foundation import Size
    from winrt.windows.storage.streams import Buffer, InputStreamOptions
    from winrt.windows.ui.notifications import KnownNotificationBindings, NotificationKinds
    from winrt.windows.ui.notifications.management import (
        UserNotificationListener, UserNotificationListenerAccessStatus as Access)
except ImportError:
    UserNotificationListener = None

ICON = 24
# applis qui ont leur propre couleur de clignotement : effet du clavier → mots reconnus
APP_FLASH = (("whatsapp", "whatsapp", ("whatsapp.com", "whatsapp.net")),
             ("snap", "snapchat", ("snapchat.com",)))   # (effet, nom, sites)
# intermédiaires : l'appli d'origine n'apparaît que dans le texte (site, téléphone relié)
RELAYS = ("edge", "chrome", "firefox", "opera", "brave", "lien avec windows", "phone link",
          "lien avec le téléphone", "mobile connecté")
BACKLOG = 3600   # au lancement, on reprend les notifications de la dernière heure
# base des notifications de Windows : le contenu complet de chaque toast. Pour un site (appli
# web Edge / Chrome), l'adresse du site n'est que là, dans l'attribut launch
WPN_DB = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Notifications\wpndatabase.db")
ORIGIN = re.compile(r"https?://([a-z0-9.-]+)", re.I)


def site_of(notif_id):
    """Site d'origine (« snapchat.com ») d'une notification de navigateur, "" si inconnu.
    Lecture seule de la base de Windows ; l'identifiant est celui du toast."""
    try:
        con = sqlite3.connect(f"file:{WPN_DB}?mode=ro", uri=True, timeout=1)
        try:
            row = con.execute("select Payload from Notification where Id = ?",
                              (int(notif_id),)).fetchone()
        finally:
            con.close()
    except (sqlite3.Error, OSError, ValueError, TypeError):
        return ""
    if not row or not row[0]:
        return ""
    payload = row[0].decode("utf-8", "replace") if isinstance(row[0], bytes) else str(row[0])
    launch = re.search(r'launch="([^"]*)"', payload)
    m = ORIGIN.search(launch.group(1) if launch else payload)
    return m.group(1).lower().removeprefix("www.") if m else ""


def _round_icon(data):
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    img = ImageOps.contain(img, (ICON, ICON), Image.LANCZOS)
    out = Image.new("RGBA", (ICON, ICON), (0, 0, 0, 0))
    out.paste(img, ((ICON - img.width) // 2, (ICON - img.height) // 2), img)
    return out


def flash_kind(item):
    """Effet du clavier pour une notification : "whatsapp", "snap" ou "notif" (blanc).
    L'appli elle-même (WhatsApp installé), le site d'une notification de navigateur
    (Snapchat dans Edge), ou un relais dont le titre ou le texte cite l'appli."""
    app = (item.get("app") or "").casefold()
    title, body = (item.get("title") or "").casefold(), (item.get("body") or "").casefold()
    site = (item.get("site") or "").casefold()
    relay = any(r in app for r in RELAYS)
    for kind, name, sites in APP_FLASH:
        if name in app:
            return kind
        # site d'origine d'une notification de navigateur (snapchat.com dans Edge)
        if site and any(site == s or site.endswith("." + s) for s in sites):
            return kind
        # relais : le nom en titre, ou le site en attribution — pas un mail qui cite l'appli
        if relay and (name in title or any(s in body for s in sites)):
            return kind
    return "notif"


class WindowsNotifications:
    def __init__(self):
        self.items = deque(maxlen=30)
        self.status = "init"
        self.last_time = 0.0       # arrivée de la dernière notification (pour le bandeau)
        self._icons = {}
        if UserNotificationListener is None:
            self.status = "paquets winrt manquants"
            return
        loop = asyncio.new_event_loop()
        threading.Thread(target=loop.run_forever, daemon=True).start()
        asyncio.run_coroutine_threadsafe(self._run(), loop)

    def clear(self):
        self.items.clear()

    async def _run(self):
        seen, first = set(), True
        while True:
            try:
                listener = UserNotificationListener.current
                if await listener.request_access_async() != Access.ALLOWED:
                    self.status = "accès refusé"
                    await asyncio.sleep(30)
                    continue
                self.status = "ok"
                notifs = await listener.get_notifications_async(NotificationKinds.TOAST)
                fresh = sorted((n for n in notifs if n.id not in seen),
                               key=lambda n: n.creation_time)
                now = time.time()
                for n in fresh:
                    seen.add(n.id)
                    item = await self._parse(n)
                    if not item or (first and now - item["time"] > BACKLOG):
                        continue
                    self.items.appendleft(item)
                    if not first:
                        self.last_time = now
                first = False
            except Exception as e:
                self.status = f"erreur : {e}"
                await asyncio.sleep(10)
            await asyncio.sleep(1.5)

    async def _parse(self, n):
        binding = n.notification.visual.get_binding(KnownNotificationBindings.toast_generic)
        texts = [t.text for t in binding.get_text_elements()] if binding else []
        texts = [t for t in texts if t and t.strip()]
        if not texts:
            return None
        info = n.app_info
        app = info.display_info.display_name if info else "Windows"
        aumid = info.app_user_model_id if info else ""
        site = ""
        if any(r in app.casefold() for r in RELAYS):
            site = site_of(n.id)
            if not site:                # toast pas encore écrit dans la base : un instant
                await asyncio.sleep(0.4)
                site = site_of(n.id)
        return {"app": app, "aumid": aumid, "site": site,
                "title": texts[0], "body": " ".join(texts[1:]),
                "icon": await self._icon(aumid, info), "time": n.creation_time.timestamp(),
                "id": n.id}

    async def _icon(self, aumid, info):
        if aumid in self._icons or not info:
            return self._icons.get(aumid)
        icon = None
        try:
            ref = info.display_info.get_logo(Size(64, 64))
            stream = await ref.open_read_async()
            buf = Buffer(stream.size)
            await stream.read_async(buf, buf.capacity, InputStreamOptions.READ_AHEAD)
            icon = _round_icon(bytes(buf))
        except Exception:
            pass
        self._icons[aumid] = icon
        return icon


if __name__ == "__main__":
    wn = WindowsNotifications()
    time.sleep(4)
    print(wn.status)
    for it in list(wn.items)[:6]:
        print(it["app"], "|", it["title"], "|", it["body"][:60], "| icône" if it["icon"] else "")
