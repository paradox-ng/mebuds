"""Icons drawn with QPainter so they look the same on every desktop and
don't depend on the icon theme (Windows has none)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QTransform,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

DATA = Path(__file__).resolve().parent / "data"
LOW_BATTERY = 15
SIZES = (16, 22, 24, 32, 48, 64)


def _foreground() -> QColor:
    return QApplication.palette().color(QPalette.WindowText)


def level_color(level: int | None) -> QColor:
    if level is None:
        return QColor(128, 128, 128)
    if level <= LOW_BATTERY:
        return QColor(218, 68, 83)  # Breeze negative red
    if level <= 35:
        return QColor(246, 116, 0)  # Breeze warning orange
    return QColor(39, 174, 96)  # Breeze positive green


def _bolt(p: QPainter, rect: QRectF, color: QColor):
    w, h = rect.width(), rect.height()
    x, y = rect.left(), rect.top()
    path = QPainterPath(QPointF(x + w * 0.60, y))
    path.lineTo(x + w * 0.15, y + h * 0.58)
    path.lineTo(x + w * 0.48, y + h * 0.58)
    path.lineTo(x + w * 0.38, y + h)
    path.lineTo(x + w * 0.85, y + h * 0.40)
    path.lineTo(x + w * 0.52, y + h * 0.40)
    path.closeSubpath()
    p.fillPath(path, color)


def _draw_bar(p: QPainter, rect: QRectF, level: int | None, charging: bool,
              fg: QColor, mono: bool):
    """One vertical battery: outline, nub on top, fill from the bottom."""
    nub_h = max(1.0, rect.height() * 0.08)
    body = QRectF(rect.left(), rect.top() + nub_h, rect.width(), rect.height() - nub_h)
    pen_w = max(1.0, rect.width() * 0.14)
    nub = QRectF(rect.center().x() - rect.width() * 0.22, rect.top(),
                 rect.width() * 0.44, nub_h + pen_w / 2)
    p.fillRect(nub, fg)
    p.setPen(QPen(fg, pen_w))
    p.setBrush(Qt.NoBrush)
    inner = body.adjusted(pen_w / 2, pen_w / 2, -pen_w / 2, -pen_w / 2)
    p.drawRoundedRect(inner, pen_w, pen_w)
    if level is None:
        return
    fill_area = inner.adjusted(pen_w, pen_w, -pen_w, -pen_w)
    frac = max(0.0, min(1.0, level / 100))
    fill = QRectF(fill_area.left(), fill_area.bottom() - fill_area.height() * frac,
                  fill_area.width(), fill_area.height() * frac)
    if mono and level > LOW_BATTERY:
        color = fg
    else:
        color = level_color(level)
    p.fillRect(fill, color)
    if charging:
        bolt = fill_area.adjusted(-pen_w, fill_area.height() * 0.2,
                                  pen_w, -fill_area.height() * 0.2)
        bg = QApplication.palette().color(QPalette.Window)
        _bolt(p, bolt.adjusted(-1, -1, 1, 1), bg)
        _bolt(p, bolt, fg if not mono else QColor(255, 196, 0))


CHARGING_GREEN = QColor(39, 174, 96)  # Breeze positive green


def _bud_path() -> QPainterPath:
    """Right earbud silhouette (head + stem) in an 11 x 22 cell."""
    head = QPainterPath()
    head.addEllipse(QPointF(0, 0), 4.7, 4.3)
    head = QTransform().translate(5.3, 6.0).rotate(-14).map(head)
    stem = QPainterPath()
    stem.addRoundedRect(QRectF(4.9, 6.5, 3.5, 14.3), 1.75, 1.75)
    return head.united(stem).simplified()


def _draw_bud(p: QPainter, level: int | None, charging: bool, fg: QColor,
              mirror: bool):
    """One bud in the current 22 x 22 coordinate space, filled from the
    bottom up to its charge."""
    path = _bud_path()
    if mirror:
        path = QTransform().translate(11, 0).scale(-1, 1).map(path)
    else:
        path = QTransform().translate(11, 0).map(path)
    if level is not None:
        if level <= LOW_BATTERY:
            color = level_color(level)
        elif charging:
            color = CHARGING_GREEN
        else:
            color = fg
        box = path.boundingRect()
        frac = max(0.08, min(1.0, level / 100))
        top = box.bottom() - box.height() * frac
        clip = QPainterPath()
        clip.addRect(QRectF(box.left() - 1, top, box.width() + 2, box.bottom() - top + 1))
        p.fillPath(path.intersected(clip), color)
    p.setPen(QPen(fg, 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)


def tray_icon(left: int | None, right: int | None, left_charging: bool = False,
              right_charging: bool = False, connected: bool = True) -> QIcon:
    """The two earbuds, each filled up to its battery level. Monochrome like
    Plasma's tray icons; red when a bud runs low, green while charging, and
    just outlines while disconnected."""
    fg = _foreground()
    if not connected:
        fg.setAlphaF(0.5)
        left = right = None
    icon = QIcon()
    for size in SIZES:
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(size / 22, size / 22)
        _draw_bud(p, left, left_charging, fg, mirror=True)
        _draw_bud(p, right, right_charging, fg, mirror=False)
        p.end()
        icon.addPixmap(pm)
    return icon


def battery_pixmap(level: int | None, charging: bool, size: int,
                   device_pixel_ratio: float = 1.0) -> QPixmap:
    """A single coloured battery for the control window."""
    w = int(size * 0.55 * device_pixel_ratio)
    h = int(size * device_pixel_ratio)
    pm = QPixmap(w, h)
    pm.setDevicePixelRatio(device_pixel_ratio)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    fg = _foreground()
    if level is None:
        fg.setAlphaF(0.45)
    _draw_bar(p, QRectF(0, 0, w / device_pixel_ratio, h / device_pixel_ratio),
              level, charging, fg, False)
    p.end()
    return pm


# The drawings' light-theme colours (see tools/gen_art.py) and what they
# become on a dark theme, so the outlines don't vanish into the background.
_DARK_SWAP = {
    "#232629": "#eff0f1",  # outline
    "#eceef0": "#3e444a",  # fill
    "#cbcfd4": "#30353a",  # shading
    "#9da2a8": "#70777e",  # speaker / case interior
}


def _is_dark_theme() -> bool:
    return QApplication.palette().color(QPalette.Window).lightness() < 128


def art_pixmap(name: str, size: int, device_pixel_ratio: float = 1.0,
               mirror: bool = False, dimmed: bool = False) -> QPixmap:
    """Render one of the SVG drawings in data/ (earbud, case, mebuds)."""
    svg = (DATA / f"{name}.svg").read_text()
    if _is_dark_theme():
        for light, dark in _DARK_SWAP.items():
            svg = svg.replace(light, dark)
    px = int(size * device_pixel_ratio)
    pm = QPixmap(px, px)
    pm.setDevicePixelRatio(device_pixel_ratio)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    if dimmed:
        p.setOpacity(0.4)
    if mirror:
        p.translate(size, 0)
        p.scale(-1, 1)
    QSvgRenderer(QByteArray(svg.encode())).render(p, QRectF(0, 0, size, size))
    p.end()
    return pm


def app_icon() -> QIcon:
    return QIcon(str(DATA / "mebuds.svg"))
