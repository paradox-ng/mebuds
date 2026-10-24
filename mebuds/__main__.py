"""Entry point: `python -m mebuds`. Launching a second copy just raises the
running one's window; two copies would fight over the control channel.

The running copy also answers `mebuds --status`, so scripts and status bars
can show the battery without opening a second connection to the earbuds.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QSettings, QTranslator
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from . import __version__

SERVER_NAME = f"mebuds-{os.getuid()}" if hasattr(os, "getuid") else "mebuds"
I18N = Path(__file__).resolve().parent / "data" / "i18n"

HELP = f"""mebuds {__version__} - control Xiaomi earbuds from the desktop

Usage: mebuds [options]

  --hidden, --tray   start in the tray without opening the window
  --status           print the earbuds' battery, from the running mebuds
  --json             with --status: print everything as JSON
  --debug            log every packet exchanged with the earbuds
  --native-style     use the desktop's widget style instead of mebuds' own
  -V, --version      print the version and exit
  -h, --help         show this help and exit

Starting mebuds while it's already running opens the running copy's window.
"""


def install_translations(app: QCoreApplication):
    """mebuds' own strings, plus Qt's for standard buttons and dialogs. The
    language is the system's unless one is picked in Settings."""
    chosen = QSettings("mebuds", "mebuds").value("language", "", type=str)
    locale = QLocale(chosen) if chosen else QLocale()
    QLocale.setDefault(locale)
    for name, folder in (("mebuds", str(I18N)),
                         ("qtbase", QLibraryInfo.path(QLibraryInfo.TranslationsPath))):
        translator = QTranslator(app)
        if translator.load(locale, name, "_", folder):
            app.installTranslator(translator)


def query_status(as_json: bool) -> int:
    app = QCoreApplication(sys.argv)  # noqa: F841 - QLocalSocket needs one
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(1000):
        print("mebuds isn't running", file=sys.stderr)
        return 1
    sock.write(b"status\n")
    sock.flush()
    data = b""
    while not data.endswith(b"\n") and sock.waitForReadyRead(3000):
        data += bytes(sock.readAll())
    if not data:
        print("mebuds didn't answer", file=sys.stderr)
        return 1
    status = json.loads(data)
    print(json.dumps(status, indent=2, ensure_ascii=False) if as_json else status["text"])
    return 0 if status.get("connected") else 2


def main() -> int:
    if "--help" in sys.argv or "-h" in sys.argv:
        print(HELP, end="")
        return 0
    if "--version" in sys.argv or "-V" in sys.argv:
        print(f"mebuds {__version__}")
        return 0
    if "--status" in sys.argv:
        return query_status("--json" in sys.argv)
    if "--debug" in sys.argv:
        # Logs every packet to stderr, for figuring out what the buds send.
        logging.basicConfig(
            level=logging.DEBUG, format="%(asctime)s %(name)s: %(message)s"
        )

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("mebuds")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("mebuds")
    app.setQuitOnLastWindowClosed(False)

    probe = QLocalSocket()
    probe.connectToServer(SERVER_NAME)
    if probe.waitForConnected(300):
        probe.write(b"show\n")
        probe.flush()
        probe.waitForBytesWritten(300)
        probe.disconnectFromServer()
        return 0
    probe.abort()

    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    server.listen(SERVER_NAME)

    install_translations(app)
    if "--native-style" not in sys.argv:
        from . import theme

        theme.apply(app)

    from .tray import App

    start_hidden = "--hidden" in sys.argv or "--tray" in sys.argv
    controller = App(app, start_hidden=start_hidden)

    def on_connection():
        conn = server.nextPendingConnection()
        if conn is None:
            return

        def on_request():
            request = bytes(conn.readAll()).strip()
            if request == b"status":
                conn.write(json.dumps(controller.status(), ensure_ascii=False).encode() + b"\n")
                conn.flush()
            else:  # "show", from a second launch
                controller.open_window()
            conn.disconnectFromServer()

        conn.readyRead.connect(on_request)
        conn.disconnected.connect(conn.deleteLater)

    server.newConnection.connect(on_connection)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
