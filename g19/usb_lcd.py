"""Écran du G19 sous Linux, en USB direct (pas de Logitech Gaming Software).

Le G19 expose son écran sur l'appareil 046d:c229, interface 0 (classe « vendeur ») :
  - sortie en masse 0x02 : une image = en-tête de 512 octets, puis 320×240 pixels RGB565
    (petit-boutiste), colonne par colonne (x d'abord, puis y de haut en bas) ;
  - entrée 0x81 : 2 octets à chaque changement des touches de l'écran (un bit par touche).
Format connu par rétro-ingénierie (projets libres autour du G19). Même interface que
lcd.G19LCD (show / update / pressed / close) : lcd.LcdThread s'en sert tel quel.

Accès sans root : règle udev installer/linux/99-g19.rules."""
import numpy as np
import usb.core
import usb.util

VENDOR, PRODUCT = 0x046D, 0xC229
W, H = 320, 240
EP_FRAME, EP_KEYS = 0x02, 0x81
# en-tête d'image : 16 octets de commande, puis 0x10…0xFF et 0x00…0xFF (512 octets en tout)
HEADER = bytes([0x10, 0x0F, 0x00, 0x58, 0x02, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x3F, 0x01, 0xEF, 0x00, 0x0F]) + \
    bytes(range(16, 256)) + bytes(range(256))
# bit → touche (à confirmer avec tools/linux_lcd_test.py)
KEY_BITS = {0x01: "menu", 0x02: "cancel", 0x04: "menu", 0x08: "ok",
            0x10: "right", 0x20: "left", 0x40: "down", 0x80: "up"}


def frame_bytes(img):
    """Image PIL → octets envoyés au G19 (en-tête compris)."""
    a = np.asarray(img.convert("RGB"), dtype=np.uint16)
    if a.shape != (H, W, 3):
        from PIL import Image
        a = np.asarray(img.convert("RGB").resize((W, H), Image.BILINEAR), dtype=np.uint16)
    px = ((a[..., 0] >> 3) << 11) | ((a[..., 1] >> 2) << 5) | (a[..., 2] >> 3)
    return HEADER + px.T.astype("<u2").tobytes()        # colonne par colonne


class G19USB:
    def __init__(self, name="PC Monitor"):
        dev = usb.core.find(idVendor=VENDOR, idProduct=PRODUCT)
        if dev is None:
            raise RuntimeError("G19 introuvable en USB (046d:c229)")
        try:
            if dev.is_kernel_driver_active(0):
                dev.detach_kernel_driver(0)
        except (usb.core.USBError, NotImplementedError):
            pass
        try:
            usb.util.claim_interface(dev, 0)
        except usb.core.USBError as e:
            if e.errno == 13:
                raise RuntimeError("accès USB refusé : installer la règle udev "
                                   "(installer/linux/99-g19.rules)") from e
            raise
        self.dev = dev
        self._last = None
        self._held = set()
        self.sent = 0
        self.raw = 0              # dernier état brut des touches (pour le test)

    def connected(self):
        return self.dev is not None

    def show(self, img):
        data = frame_bytes(img)
        if data == self._last:
            return
        self._last = data
        self.dev.write(EP_FRAME, data, timeout=1000)
        self.sent += 1

    def update(self):
        pass                      # l'image part dès show()

    def _read_keys(self, timeout=10):
        try:
            data = self.dev.read(EP_KEYS, 2, timeout=timeout)
        except usb.core.USBTimeoutError:
            return None
        except usb.core.USBError as e:
            if e.errno in (110, None):          # délai dépassé selon libusb
                return None
            raise
        self.raw = data[0] | (data[1] << 8 if len(data) > 1 else 0)
        return self.raw

    def pressed(self):
        """Touches nouvellement enfoncées depuis le dernier appel."""
        raw = self._read_keys()
        if raw is None:
            return set()
        held = {name for bit, name in KEY_BITS.items() if raw & bit}
        new = held - self._held
        self._held = held
        return new

    def close(self):
        try:
            usb.util.release_interface(self.dev, 0)
            usb.util.dispose_resources(self.dev)
        except usb.core.USBError:
            pass
