"""Briques Qt de l'utilitaire (config_g19.pyw) : feuille de style tirée des palettes du G19,
interrupteur, pastille de couleur, cartes de réglages et liaison champ ↔ réglage."""
import ctypes
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, Property, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractButton, QComboBox, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QSlider, QSpinBox, QAbstractSpinBox, QVBoxLayout,
                               QWidget, QPushButton)

from .theme import PALETTES

ASSETS = Path(tempfile.gettempdir()) / "g19_qt_assets"


def hexa(c):
    return "#%02x%02x%02x" % tuple(c[:3])


def mix(a, b, f):
    return tuple(int(x + (y - x) * f) for x, y in zip(a, b))


def palette(name):
    p = dict(PALETTES.get(name) or PALETTES["dark"])
    light = sum(p["BG"]) > 380
    p["LINE"] = mix(p["PANEL"], p["TEXT"], 0.12)
    p["SIDE"] = mix(p["BG"], p["PANEL"], 0.45)
    p["SEL"] = mix(p["PANEL"], p["ACCENT"], 0.16 if not light else 0.12)
    p["HOT"] = (230, 80, 80) if not light else (200, 40, 40)
    p["LIGHT"] = light
    return p


def _assets(p, name):
    """Petites images de la feuille de style (flèche des listes, coche) aux couleurs du thème."""
    folder = ASSETS / name
    folder.mkdir(parents=True, exist_ok=True)
    arrow = folder / "arrow.png"
    check = folder / "check.png"
    if not arrow.exists():
        img = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.line([(10, 15), (20, 25), (30, 15)], fill=p["MUTED"] + (255,), width=4)
        img.resize((10, 10), Image.LANCZOS).save(arrow)
    if not check.exists():
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.line([(14, 33), (27, 46), (50, 18)], fill=p["ON_ACCENT"] + (255,), width=8)
        img.resize((16, 16), Image.LANCZOS).save(check)
    return arrow.as_posix(), check.as_posix()


def stylesheet(name):
    p = palette(name)
    c = {k: hexa(v) for k, v in p.items() if isinstance(v, tuple) and len(v) == 3}
    arrow, check = _assets(p, name)
    return f"""
    * {{ font-family: "Segoe UI Variable Text", "Segoe UI"; font-size: 10pt; color: {c['TEXT']}; }}
    QMainWindow, #root {{ background: {c['BG']}; }}
    #side {{ background: {c['SIDE']}; border-right: 1px solid {c['LINE']}; }}
    #side QListWidget {{ background: transparent; border: none; outline: none; }}
    #side QListWidget::item {{ padding: 0 10px; margin: 2px 8px; border-radius: 7px;
                               color: {c['MUTED']}; }}
    #side QListWidget::item:hover {{ background: {c['HOVER']}; color: {c['TEXT']}; }}
    #side QListWidget::item:selected {{ background: {c['SEL']}; color: {c['TEXT']}; }}
    #brand {{ font-size: 15pt; font-weight: 600; }}
    #brandSub, #muted, #hint {{ color: {c['MUTED']}; }}
    #hint {{ font-size: 9pt; }}
    #pageTitle {{ font-size: 18pt; font-weight: 600; }}
    #pageHint {{ color: {c['MUTED']}; }}
    #section {{ color: {c['ACCENT']}; font-size: 8.5pt; font-weight: 700; letter-spacing: 1px; }}
    #card {{ background: {c['PANEL']}; border: 1px solid {c['LINE']}; border-radius: 10px; }}
    #card QLabel {{ background: transparent; }}
    #rowSep {{ background: {c['LINE']}; max-height: 1px; min-height: 1px; border: none; }}
    #pill {{ border-radius: 9px; padding: 2px 10px; font-size: 9pt; font-weight: 600; }}
    #pillOn {{ background: {hexa(mix(p['PANEL'], p['OK'], 0.25))}; color: {c['OK']};
               border-radius: 9px; padding: 2px 10px; font-size: 9pt; font-weight: 600; }}
    #pillOff {{ background: {c['FIELD']}; color: {c['MUTED']};
                border-radius: 9px; padding: 2px 10px; font-size: 9pt; font-weight: 600; }}
    #dirty {{ color: {c['CLAUDE']}; font-weight: 600; }}
    #status {{ color: {c['MUTED']}; }}
    #bottom, #top {{ background: {c['BG']}; }}
    #top {{ border-bottom: 1px solid {c['LINE']}; }}
    #bottom {{ border-top: 1px solid {c['LINE']}; }}
    #previewFrame {{ background: {c['BG']}; border: 2px solid {c['ACCENT']}; border-radius: 6px; }}
    #previewBox {{ background: {c['PANEL']}; border: 1px solid {c['LINE']}; border-radius: 10px; }}
    QPushButton {{ background: {c['FIELD']}; border: 1px solid {c['LINE']}; border-radius: 6px;
                   padding: 6px 14px; }}
    QPushButton:hover {{ background: {c['HOVER']}; }}
    QPushButton:pressed {{ background: {c['TRACK']}; }}
    QPushButton:disabled {{ color: {c['MUTED']}; background: {c['PANEL']}; }}
    QPushButton#accent {{ background: {c['ACCENT']}; color: {c['ON_ACCENT']}; border: none;
                          font-weight: 600; }}
    QPushButton#accent:hover {{ background: {hexa(mix(p['ACCENT'], p['TEXT'], 0.15))}; }}
    QPushButton#key {{ padding: 6px 4px; min-width: 38px; font-weight: 600; }}
    QPushButton#flat {{ background: transparent; border: none; color: {c['ACCENT']}; padding: 4px 6px; }}
    QPushButton#flat:hover {{ text-decoration: underline; }}
    QLineEdit, QSpinBox, QComboBox {{ background: {c['FIELD']}; border: 1px solid {c['LINE']};
        border-radius: 6px; padding: 5px 8px; selection-background-color: {c['ACCENT']};
        selection-color: {c['ON_ACCENT']}; }}
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {c['ACCENT']}; }}
    QSpinBox QLineEdit {{ padding: 0; border: none; background: transparent; }}
    QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; subcontrol-origin: margin; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox::down-arrow {{ image: url({arrow}); width: 10px; height: 10px; }}
    QComboBox QAbstractItemView {{ background: {c['PANEL']}; border: 1px solid {c['LINE']};
        selection-background-color: {c['SEL']}; selection-color: {c['TEXT']}; outline: none;
        padding: 4px; }}
    QListWidget, QTableWidget {{ background: {c['FIELD']}; border: 1px solid {c['LINE']};
        border-radius: 8px; outline: none; alternate-background-color: {c['PANEL']}; }}
    QListWidget::item {{ padding: 5px 6px; }}
    QListWidget::item:selected, QTableWidget::item:selected {{ background: {c['SEL']};
        color: {c['TEXT']}; }}
    QListWidget::indicator {{ width: 16px; height: 16px; }}
    QRadioButton {{ spacing: 8px; background: transparent; }}
    QRadioButton::indicator {{ width: 14px; height: 14px; }}
    QListWidget::indicator:unchecked {{ background: {c['FIELD']}; border: 1px solid {c['TRACK']};
        border-radius: 4px; }}
    QListWidget::indicator:checked {{ background: {c['ACCENT']}; border: 1px solid {c['ACCENT']};
        border-radius: 4px; image: url({check}); }}
    QRadioButton::indicator:unchecked {{ border: 2px solid {c['TRACK']}; border-radius: 9px;
        background: {c['FIELD']}; }}
    QRadioButton::indicator:checked {{ border: 2px solid {c['ACCENT']}; border-radius: 9px;
        background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
            stop:0 {c['ACCENT']}, stop:0.5 {c['ACCENT']}, stop:0.6 {c['FIELD']}, stop:1 {c['FIELD']}); }}
    QHeaderView::section {{ background: {c['PANEL']}; color: {c['MUTED']}; border: none;
        border-bottom: 1px solid {c['LINE']}; padding: 5px 6px; font-weight: 600; }}
    QTableCornerButton::section {{ background: {c['PANEL']}; border: none; }}
    QSlider::groove:horizontal {{ height: 4px; background: {c['TRACK']}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {c['ACCENT']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {c['TEXT']}; width: 14px; height: 14px;
        margin: -6px 0; border-radius: 7px; border: 3px solid {c['ACCENT']}; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {c['TRACK']}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {c['MUTED']}; }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
        background: none; height: 0; }}
    QToolTip {{ background: {c['PANEL']}; color: {c['TEXT']}; border: 1px solid {c['LINE']};
        padding: 4px; }}
    QMenu {{ background: {c['PANEL']}; border: 1px solid {c['LINE']}; }}
    QMenu::item:selected {{ background: {c['SEL']}; }}
    QMessageBox, QDialog {{ background: {c['BG']}; }}
    """


def title_bar(widget, name):
    """Barre de titre Windows assortie : sombre ou claire, et teinte du fond (Windows 11)."""
    p = palette(name)
    try:
        hwnd = int(widget.winId())
        dwm = ctypes.windll.dwmapi
        dark = ctypes.c_int(0 if p["LIGHT"] else 1)
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), 4)
        r, g, b = p["BG"]
        caption = ctypes.c_int(r | (g << 8) | (b << 16))
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), 4)
        text = ctypes.c_int(p["TEXT"][0] | (p["TEXT"][1] << 8) | (p["TEXT"][2] << 16))
        dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text), 4)
    except Exception:
        pass


def glyph_icon(char, normal, selected, size=18):
    """Icône dessinée avec la police d'icônes de Windows (Segoe Fluent Icons, sinon MDL2),
    une couleur au repos et une autre quand l'entrée est choisie."""
    from PySide6.QtGui import QFont, QIcon
    icon = QIcon()
    for color, mode in ((normal, QIcon.Normal), (selected, QIcon.Selected),
                        (selected, QIcon.Active)):
        px = QPixmap(size * 2, size * 2)
        px.fill(Qt.transparent)
        qp = QPainter(px)
        qp.setRenderHint(QPainter.Antialiasing)
        qp.setRenderHint(QPainter.TextAntialiasing)
        f = QFont("Segoe Fluent Icons")
        if not f.exactMatch():
            f = QFont("Segoe MDL2 Assets")
        f.setPixelSize(int(size * 1.55))
        qp.setFont(f)
        qp.setPen(QColor(*color))
        qp.drawText(px.rect(), Qt.AlignCenter, char)
        qp.end()
        px.setDevicePixelRatio(2)
        icon.addPixmap(px, mode)
    return icon


def pil_to_pixmap(img):
    img = img.convert("RGBA")
    q = QImage(img.tobytes("raw", "RGBA"), img.width, img.height, QImage.Format_RGBA8888)
    return QPixmap.fromImage(q.copy())


# --- widgets ---

class Toggle(QAbstractButton):
    """Interrupteur façon Windows 11 (case à cocher)."""

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(42, 22)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)   # pas « pos » : la position du widget
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)
        self.colors = palette("dark")

    def _animate(self, on):
        self._anim.stop()
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _get_pos(self):
        return self._pos

    def _set_pos(self, v):
        self._pos = v
        self.update()

    knob = Property(float, _get_pos, _set_pos)

    def setChecked(self, on):
        super().setChecked(on)
        self._pos = 1.0 if on else 0.0
        self.update()

    def sizeHint(self):
        return QSize(42, 22)

    def paintEvent(self, _e):
        p = self.colors
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        on = QColor(*p["ACCENT"])
        off = QColor(*p["FIELD"])
        track = QColor(
            *[int(a + (b - a) * self._pos) for a, b in zip(off.getRgb()[:3], on.getRgb()[:3])])
        qp.setPen(QColor(*p["TRACK"]) if self._pos < 0.5 else Qt.NoPen)
        qp.setBrush(track)
        qp.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 8
        x = r.left() + 4 + (r.width() - 8 - d) * self._pos
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(*p["ON_ACCENT"]) if self._pos >= 0.5 else QColor(*p["MUTED"]))
        qp.drawEllipse(QRectF(x, r.top() + 4, d, d))


class Swatch(QPushButton):
    """Pastille de couleur cliquable ("" : aucune, affiche un tiret)."""
    changed = Signal(str)

    def __init__(self, color="", parent=None):
        super().__init__(parent)
        self.setFixedSize(34, 24)
        self.setCursor(Qt.PointingHandCursor)
        self.set(color)

    def set(self, color):
        self.color = color or ""
        self.setText("" if self.color else "—")
        self.setStyleSheet(f"background: {self.color}; border-radius: 6px;" if self.color else
                           "border-radius: 6px;")


def label(text, name=None, wrap=False):
    w = QLabel(text)
    if name:
        w.setObjectName(name)
    if wrap:
        w.setWordWrap(True)
    return w


class Card(QFrame):
    """Carte de réglages : titre en petites capitales, puis des lignes libellé / contrôle."""

    def __init__(self, title=None, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(18, 14, 18, 14)
        self.lay.setSpacing(0)
        self._rows = 0
        if title:
            t = label(title.upper(), "section")
            self.lay.addWidget(t)
            self.lay.addSpacing(6)

    def _sep(self):
        if self._rows:
            line = QFrame()
            line.setObjectName("rowSep")
            self.lay.addSpacing(8)
            self.lay.addWidget(line)
        self.lay.addSpacing(8)
        self._rows += 1

    def row(self, text, control, hint=None):
        """Libellé (et aide dessous) à gauche, contrôle à droite."""
        self._sep()
        line = QHBoxLayout()
        line.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(2)
        left.addWidget(label(text, wrap=True))
        if hint:
            left.addWidget(label(hint, "hint", wrap=True))
        line.addLayout(left, 1)
        if isinstance(control, QWidget):
            line.addWidget(control, 0, Qt.AlignRight | Qt.AlignVCenter)
        else:
            line.addLayout(control, 0)
        self.lay.addLayout(line)
        return control

    def widget(self, w):
        """Bloc pleine largeur (liste, tableau, texte)."""
        self._sep()
        self.lay.addWidget(w)
        return w

    def note(self, text):
        self.lay.addSpacing(8)
        w = label(text, "hint", wrap=True)
        self.lay.addWidget(w)
        return w


def hbox(*widgets, spacing=6, stretch=False):
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(0, 0, 0, 0)
    for w in widgets:
        if isinstance(w, QWidget):
            lay.addWidget(w)
        else:
            lay.addLayout(w)
    if stretch:
        lay.addStretch(1)
    box = QWidget()          # sans fond propre : celui de la carte reste visible
    box.setLayout(lay)
    return box


def spin(lo, hi, step=1, suffix="", width=84):
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setButtonSymbols(QAbstractSpinBox.NoButtons)
    s.setAlignment(Qt.AlignRight)
    if suffix:
        s.setSuffix(f" {suffix}")
    s.setFixedWidth(width)
    return s


def combo(items, width=None):
    """items : [(valeur, libellé)]."""
    c = QComboBox()
    for value, text in items:
        c.addItem(text, value)
    if width:
        c.setFixedWidth(width)
    return c


def line_edit(text="", width=None, secret=False, placeholder=""):
    e = QLineEdit(text)
    if width:
        e.setFixedWidth(width)
    if secret:
        e.setEchoMode(QLineEdit.Password)
    if placeholder:
        e.setPlaceholderText(placeholder)
    return e


def slider(lo, hi, step, fmt="{} %", width=190):
    """Curseur avec sa valeur à droite ; renvoie (conteneur, QSlider)."""
    s = QSlider(Qt.Horizontal)
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setPageStep(step)
    s.setFixedWidth(width)
    value = label("", "muted")
    value.setFixedWidth(58)
    value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def moved(v):
        snapped = int(round(v / step) * step)
        if snapped != v:
            s.setValue(snapped)
            return
        value.setText(fmt.format(v))

    s.valueChanged.connect(moved)
    moved(s.value())
    return hbox(s, value), s


# --- liaison champ ↔ réglage ---

class Field:
    """Un réglage affiché : get() la valeur à enregistrer, set(v) l'affiche."""

    def __init__(self, get, set_, on_change=None):
        self.get, self.set = get, set_
        self.on_change = on_change


def bind_toggle(w):
    return Field(w.isChecked, lambda v: w.setChecked(bool(v)))


def bind_spin(w):
    return Field(w.value, lambda v: w.setValue(int(v)))


def bind_slider(s):
    return Field(s.value, lambda v: s.setValue(int(v)))


def bind_combo(c, default=None):
    def get():
        v = c.currentData()
        return default if v is None else v

    def set_(v):
        i = c.findData(v)
        c.setCurrentIndex(i if i >= 0 else 0)
    return Field(get, set_)


def bind_text(e, strip=True):
    return Field(lambda: e.text().strip() if strip else e.text(), lambda v: e.setText(v or ""))


def bind_swatch(w):
    return Field(lambda: w.color, w.set)
