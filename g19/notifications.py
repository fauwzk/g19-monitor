"""Notifications Windows (toasts de toutes les applis) via UserNotificationListener.

L'accès se règle dans Paramètres → Confidentialité et sécurité → Notifications.
"""
import asyncio
import io
import threading
import time
from collections import deque

from PIL import Image, ImageDraw, ImageOps

try:
    from winrt.windows.foundation import Size
    from winrt.windows.storage.streams import Buffer, InputStreamOptions
    from winrt.windows.ui.notifications import KnownNotificationBindings, NotificationKinds
    from winrt.windows.ui.notifications.management import (
        UserNotificationListener, UserNotificationListenerAccessStatus as Access)
except ImportError:
    UserNotificationListener = None

ICON = 24
BACKLOG = 3600   # au lancement, on reprend les notifications de la dernière heure


def _round_icon(data):
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    img = ImageOps.contain(img, (ICON, ICON), Image.LANCZOS)
    out = Image.new("RGBA", (ICON, ICON), (0, 0, 0, 0))
    out.paste(img, ((ICON - img.width) // 2, (ICON - img.height) // 2), img)
    return out


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
        return {"app": app, "title": texts[0], "body": " ".join(texts[1:]),
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
