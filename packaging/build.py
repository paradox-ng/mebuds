"""Build a standalone mebuds for this machine's OS and CPU.

    python packaging/build.py

Linux gets an AppImage, Windows a zip with mebuds.exe inside. Output goes to
dist/. Needs PySide6 and PyInstaller installed; on Linux it also downloads
appimagetool.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "packaging"
BUILD = ROOT / "build"
DIST = ROOT / "dist"
APP = "mebuds"

APPIMAGETOOL = (
    "https://github.com/AppImage/appimagetool/releases/download/continuous/"
    "appimagetool-{arch}.AppImage"
)


def version() -> str:
    text = (ROOT / "mebuds" / "__init__.py").read_text()
    return re.search(r'__version__ = "(.+?)"', text).group(1)


def arch() -> str:
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x64" if sys.platform == "win32" else "x86_64"
    if machine in ("aarch64", "arm64"):
        return "arm64" if sys.platform == "win32" else "aarch64"
    sys.exit(f"unsupported CPU: {platform.machine()}")


def make_icons(out: Path) -> tuple[Path, Path]:
    """Render the SVG app icon to a 256px PNG and a multi-size .ico."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    renderer = QSvgRenderer(str(ROOT / "mebuds" / "data" / "mebuds.svg"))

    def png(size: int) -> bytes:
        img = QImage(size, size, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        renderer.render(p, QRectF(0, 0, size, size))
        p.end()
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "PNG")
        return bytes(data)

    out.mkdir(parents=True, exist_ok=True)
    png_path = out / f"{APP}.png"
    png_path.write_bytes(png(256))

    # ICO with PNG-compressed entries, which Windows has read since Vista.
    sizes = (16, 24, 32, 48, 64, 128, 256)
    images = [png(s) for s in sizes]
    header = (0).to_bytes(2, "little") + (1).to_bytes(2, "little") + len(sizes).to_bytes(2, "little")
    offset = 6 + 16 * len(sizes)
    entries = b""
    for size, data in zip(sizes, images):
        dim = 0 if size == 256 else size
        entries += bytes([dim, dim, 0, 0]) + (1).to_bytes(2, "little") + (32).to_bytes(2, "little")
        entries += len(data).to_bytes(4, "little") + offset.to_bytes(4, "little")
        offset += len(data)
    ico_path = out / f"{APP}.ico"
    ico_path.write_bytes(header + entries + b"".join(images))
    return png_path, ico_path


def pyinstaller(ico: Path) -> Path:
    args = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP,
        "--windowed",
        "--noconfirm",
        "--clean",
        "--paths", str(ROOT),
        "--distpath", str(BUILD / "pyinstaller"),
        "--workpath", str(BUILD / "pyi-work"),
        "--specpath", str(BUILD),
        "--add-data", f"{ROOT / 'mebuds' / 'data'}{os.pathsep}mebuds/data",
    ]
    if sys.platform == "win32":
        args += ["--icon", str(ico)]
    subprocess.run(args + [str(HERE / "launcher.py")], check=True)
    return BUILD / "pyinstaller" / APP


def appimage(bundle: Path, png: Path, out: Path):
    appdir = BUILD / "AppDir"
    shutil.copytree(bundle, appdir / "usr" / "bin", dirs_exist_ok=True)
    svg = ROOT / "mebuds" / "data" / f"{APP}.svg"
    icons = appdir / "usr" / "share" / "icons" / "hicolor"
    (icons / "scalable" / "apps").mkdir(parents=True)
    shutil.copy(svg, icons / "scalable" / "apps" / f"{APP}.svg")
    (icons / "256x256" / "apps").mkdir(parents=True)
    shutil.copy(png, icons / "256x256" / "apps" / f"{APP}.png")
    (appdir / "usr" / "share" / "applications").mkdir(parents=True)
    shutil.copy(HERE / f"{APP}.desktop", appdir / "usr" / "share" / "applications")
    shutil.copy(HERE / f"{APP}.desktop", appdir)
    shutil.copy(svg, appdir / f"{APP}.svg")
    (appdir / ".DirIcon").symlink_to(f"{APP}.svg")
    apprun = appdir / "AppRun"
    apprun.write_text(
        '#!/bin/sh\nHERE="$(dirname "$(readlink -f "$0")")"\n'
        f'exec "$HERE/usr/bin/{APP}" "$@"\n'
    )
    apprun.chmod(apprun.stat().st_mode | stat.S_IEXEC)

    tool = BUILD / "appimagetool.AppImage"
    urllib.request.urlretrieve(APPIMAGETOOL.format(arch=arch()), tool)
    tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
    env = dict(os.environ, ARCH=arch())
    subprocess.run([str(tool), "--appimage-extract-and-run", str(appdir), str(out)],
                   check=True, env=env)


def zip_dir(folder: Path, out: Path):
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(folder.rglob("*")):
            z.write(path, Path(APP) / path.relative_to(folder))


def main():
    if sys.platform.startswith("linux"):
        import socket

        if not hasattr(socket, "AF_BLUETOOTH"):
            # The app would build fine and then never connect.
            sys.exit("this Python has no Bluetooth socket support; build with "
                     "a distribution Python (e.g. Debian/Ubuntu's python3)")
    shutil.rmtree(BUILD, ignore_errors=True)
    DIST.mkdir(exist_ok=True)
    png, ico = make_icons(BUILD / "icons")
    bundle = pyinstaller(ico)
    name = f"{APP}-{version()}"
    if sys.platform == "win32":
        out = DIST / f"{name}-windows-{arch()}.zip"
        zip_dir(bundle, out)
    elif sys.platform.startswith("linux"):
        out = DIST / f"{name}-linux-{arch()}.AppImage"
        appimage(bundle, png, out)
    else:
        sys.exit(f"unsupported OS: {sys.platform}")
    print(f"built {out}")


if __name__ == "__main__":
    main()
