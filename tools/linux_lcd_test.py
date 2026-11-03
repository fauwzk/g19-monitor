"""Test de l'écran du G19 sous Linux : mire + touches, 30 s (Ctrl+C pour arrêter plus tôt).

    python3 tools/linux_lcd_test.py

Sur le G19 : un carré ROUGE en haut à gauche, VERT en haut à droite, BLEU en bas à gauche,
des bandes de couleur et une barre qui défile. Dans le terminal : chaque touche de l'écran
appuyée (code brut + nom supposé), puis la fluidité obtenue."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from g19.usb_lcd import KEY_BITS, G19USB, W, H  # noqa: E402

SECONDS = 30


def font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def pattern(t, frames, keys):
    img = Image.new("RGB", (W, H), (18, 22, 30))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 59, 39), fill=(230, 40, 40))
    d.text((4, 12), "HAUT G", font=font(13), fill=(255, 255, 255))
    d.rectangle((W - 60, 0, W - 1, 39), fill=(40, 200, 70))
    d.text((W - 56, 12), "HAUT D", font=font(13), fill=(0, 0, 0))
    d.rectangle((0, H - 40, 59, H - 1), fill=(50, 90, 240))
    d.text((4, H - 28), "BAS G", font=font(13), fill=(255, 255, 255))
    d.text((W // 2, 70), "G19 sous Linux", font=font(24), fill=(255, 255, 255), anchor="mm")
    d.text((W // 2, 100), f"image {frames}", font=font(14), fill=(170, 180, 200), anchor="mm")
    d.text((W // 2, 124), "touches : " + (" ".join(sorted(keys)) or "—"), font=font(14),
           fill=(255, 210, 80), anchor="mm")
    # bandes : dégradés rouge, vert, bleu, gris (montrent la précision des couleurs)
    for k, col in enumerate(((1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 1))):
        for x in range(W):
            v = int(255 * x / (W - 1))
            d.line((x, 146 + k * 12, x, 156 + k * 12), fill=tuple(v * c for c in col))
    # barre qui défile : saccades visibles, fluidité mesurée
    x = int((t * 160) % W)
    d.rectangle((x - 20, 200, x + 20, 214), fill=(255, 255, 255))
    return img


def main():
    try:
        lcd = G19USB()
    except RuntimeError as e:
        print("Échec :", e)
        return 1
    print("G19 trouvé. Mire affichée pendant", SECONDS, "s. Appuie sur chaque touche de "
          "l'écran (Menu, Annuler, ▲ ▼ ◄ ►, OK).")
    start = time.time()
    frames, held, names = 0, 0, set()
    try:
        while time.time() - start < SECONDS:
            lcd.show(pattern(time.time() - start, frames, names))
            frames += 1
            raw = lcd._read_keys(timeout=1)
            if raw is not None and raw != held:
                held = raw
                names = {n for b, n in KEY_BITS.items() if raw & b}
                print(f"  touches : brut 0x{raw:04x}  bits {[hex(b) for b in KEY_BITS if raw & b]}"
                      f"  → {', '.join(sorted(names)) or 'relâchées'}")
    except KeyboardInterrupt:
        pass
    finally:
        span = time.time() - start
        print(f"{frames} images en {span:.1f} s : {frames / span:.1f} images/s")
        lcd.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
