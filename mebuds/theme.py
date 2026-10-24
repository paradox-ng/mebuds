"""mebuds' own look: Qt's Fusion style with Breeze-like colours and a
stylesheet on top. Fusion is part of every Qt, including the one bundled in
the AppImage and the Windows build, so the app looks the same everywhere
instead of depending on which style plugins the system has.

Follows the system's light/dark preference and switches when it changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory


@dataclass(frozen=True)
class Colors:
    window: str
    text: str
    base: str
    alt_base: str
    button: str
    card: str
    border: str
    disabled_text: str
    accent: str
    accent_text: str
    link: str


# Colours from KDE's Breeze and Breeze Dark schemes.
LIGHT = Colors(
    window="#eff0f1", text="#232629", base="#ffffff", alt_base="#f7f7f7",
    button="#fcfcfc", card="#fafafa", border="#bdc3c7",
    disabled_text="#a0a4a8", accent="#3daee9", accent_text="#ffffff",
    link="#2980b9",
)
DARK = Colors(
    window="#202326", text="#fcfcfc", base="#141618", alt_base="#1d1f22",
    button="#292c30", card="#272a2e", border="#3f4347",
    disabled_text="#70747a", accent="#3daee9", accent_text="#fcfcfc",
    link="#1d99f3",
)


def _palette(c: Colors) -> QPalette:
    p = QPalette()
    roles = {
        QPalette.Window: c.window,
        QPalette.WindowText: c.text,
        QPalette.Base: c.base,
        QPalette.AlternateBase: c.alt_base,
        QPalette.Button: c.button,
        QPalette.ButtonText: c.text,
        QPalette.Text: c.text,
        QPalette.ToolTipBase: c.button,
        QPalette.ToolTipText: c.text,
        QPalette.Highlight: c.accent,
        QPalette.HighlightedText: c.accent_text,
        QPalette.Link: c.link,
        QPalette.PlaceholderText: c.disabled_text,
        QPalette.Light: c.button,
        QPalette.Midlight: c.button,
        QPalette.Mid: c.border,
        QPalette.Dark: c.border,
        QPalette.Shadow: "#000000",
    }
    for role, color in roles.items():
        p.setColor(role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(c.disabled_text))
    p.setColor(QPalette.Disabled, QPalette.Highlight, QColor(c.border))
    return p


UI = Path(__file__).resolve().parent / "data" / "ui"


def _stylesheet(c: Colors) -> str:
    dark = c is DARK
    chevron = (UI / ("chevron-dark.svg" if dark else "chevron-light.svg")).as_posix()
    check = (UI / "check.svg").as_posix()
    return f"""
    QPushButton, QComboBox {{
        background: {c.button};
        border: 1px solid {c.border};
        border-radius: 5px;
        padding: 5px 12px;
    }}
    QPushButton:hover, QComboBox:hover {{ border-color: {c.accent}; }}
    QPushButton:pressed {{ background: {c.accent}; color: {c.accent_text}; }}
    QPushButton:disabled, QComboBox:disabled {{ color: {c.disabled_text}; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox::down-arrow {{ image: url("{chevron}"); width: 14px; height: 14px; }}

    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px;
        border: 1px solid {c.border};
        border-radius: 4px;
        background: {c.base};
    }}
    QCheckBox::indicator:hover {{ border-color: {c.accent}; }}
    QCheckBox::indicator:checked {{
        background: {c.accent};
        border-color: {c.accent};
        image: url("{check}");
    }}
    QCheckBox::indicator:disabled {{ background: {c.window}; }}
    QCheckBox::indicator:checked:disabled {{ background: {c.border}; border-color: {c.border}; }}

    QSlider::groove:vertical {{
        width: 4px;
        border-radius: 2px;
        background: {c.border};
    }}
    QSlider::add-page:vertical {{ width: 4px; border-radius: 2px; background: {c.accent}; }}
    QSlider::sub-page:vertical {{ width: 4px; border-radius: 2px; background: {c.border}; }}
    QSlider::handle:vertical {{
        height: 16px;
        margin: 0 -6px;
        border-radius: 8px;
        background: {c.button};
        border: 1px solid {c.accent};
    }}
    QSlider::handle:vertical:hover {{ background: {c.accent}; }}
    QComboBox QAbstractItemView {{
        background: {c.base};
        border: 1px solid {c.border};
        selection-background-color: {c.accent};
        selection-color: {c.accent_text};
        outline: none;
    }}

    QTabWidget::pane {{
        border: 1px solid {c.border};
        border-radius: 6px;
        top: -1px;
        background: {c.window};
    }}
    QTabBar::tab {{
        padding: 6px 14px;
        border: 1px solid transparent;
        border-bottom: none;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        color: {c.text};
    }}
    QTabBar::tab:selected {{
        background: {c.window};
        border-color: {c.border};
        border-top: 2px solid {c.accent};
    }}
    QTabBar::tab:!selected:hover {{ color: {c.accent}; }}

    QFrame#card {{
        background: {c.card};
        border: 1px solid {c.border};
        border-radius: 10px;
    }}
    QFrame#card QLabel {{ background: transparent; }}

    QMenu {{
        background: {c.base};
        border: 1px solid {c.border};
        border-radius: 6px;
        padding: 4px;
    }}
    QMenu::item {{ padding: 5px 24px 5px 12px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {c.accent}; color: {c.accent_text}; }}
    QMenu::item:disabled {{ color: {c.disabled_text}; background: transparent; }}
    QMenu::separator {{ height: 1px; background: {c.border}; margin: 4px 8px; }}
    QMenu::indicator {{ width: 14px; height: 14px; }}

    QToolTip {{
        background: {c.button};
        color: {c.text};
        border: 1px solid {c.border};
        padding: 4px;
    }}
    """


def is_dark(app: QApplication) -> bool:
    scheme = app.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Dark:
        return True
    if scheme == Qt.ColorScheme.Light:
        return False
    # Unknown: go by what the platform's own palette looks like.
    return app.style().standardPalette().color(QPalette.Window).lightness() < 128


def apply(app: QApplication):
    app.setStyle(QStyleFactory.create("Fusion"))

    def update(*_):
        colors = DARK if is_dark(app) else LIGHT
        app.setPalette(_palette(colors))
        app.setStyleSheet(_stylesheet(colors))

    update()
    app.styleHints().colorSchemeChanged.connect(update)
