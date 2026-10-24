"""Start mebuds at login: an XDG autostart entry on Linux, the per-user Run
key on Windows. The entry itself is the source of truth for both settings."""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

NAME = "mebuds"
HIDDEN_FLAG = "--hidden"
ROOT = Path(__file__).resolve().parents[1]


def _command() -> list[str]:
    """How to start this copy of mebuds again."""
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        return [appimage]
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, str(ROOT / "packaging" / "launcher.py")]


# ----- Linux (XDG autostart) -----
def _desktop_file() -> Path:
    config = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(config) / "autostart" / f"{NAME}.desktop"


def _linux_exec() -> str | None:
    try:
        for line in _desktop_file().read_text().splitlines():
            if line.startswith("Exec="):
                return line[len("Exec="):]
    except OSError:
        pass
    return None


def _linux_set(enabled: bool, hidden: bool):
    path = _desktop_file()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    args = _command() + ([HIDDEN_FLAG] if hidden else [])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={NAME}\n"
        "Comment=Battery and settings for Xiaomi earbuds\n"
        f"Exec={shlex.join(args)}\n"
        "Icon=audio-headphones\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


# ----- Windows (HKCU Run key) -----
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _windows_exec() -> str | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            return winreg.QueryValueEx(key, NAME)[0]
    except OSError:
        return None


def _windows_set(enabled: bool, hidden: bool):
    import subprocess
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if not enabled:
            try:
                winreg.DeleteValue(key, NAME)
            except FileNotFoundError:
                pass
            return
        args = _command() + ([HIDDEN_FLAG] if hidden else [])
        winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(args))


# ----- public -----
def _current() -> str | None:
    return _windows_exec() if sys.platform == "win32" else _linux_exec()


def is_enabled() -> bool:
    return _current() is not None


def starts_hidden() -> bool:
    entry = _current()
    return entry is None or HIDDEN_FLAG in entry


def set_enabled(enabled: bool, hidden: bool = True):
    if sys.platform == "win32":
        _windows_set(enabled, hidden)
    else:
        _linux_set(enabled, hidden)
