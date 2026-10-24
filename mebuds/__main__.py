"""Entry point: `python -m mebuds`. Launching a second copy just raises the
running one's window; two copies would fight over the control channel."""

from __future__ import annotations

import logging
import os
import sys

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from . import __version__

SERVER_NAME = f"mebuds-{os.getuid()}" if hasattr(os, "getuid") else "mebuds"


def main() -> int:
    if "--version" in sys.argv or "-V" in sys.argv:
        print(f"mebuds {__version__}")
        return 0
    if "--debug" in sys.argv:
        # Logs every packet to stderr, for figuring out what the buds send.
        logging.basicConfig(
            level=logging.DEBUG, format="%(asctime)s %(name)s: %(message)s"
        )

    app = QApplication(sys.argv)
    app.setApplicationName("mebuds")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("mebuds")
    app.setQuitOnLastWindowClosed(False)

    probe = QLocalSocket()
    probe.connectToServer(SERVER_NAME)
    if probe.waitForConnected(300):
        probe.write(b"show")
        probe.flush()
        probe.waitForBytesWritten(300)
        probe.disconnectFromServer()
        return 0
    probe.abort()

    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    server.listen(SERVER_NAME)

    from .tray import App

    start_hidden = "--hidden" in sys.argv or "--tray" in sys.argv
    controller = App(app, start_hidden=start_hidden)

    def on_second_launch():
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.disconnectFromServer()
        controller.open_window()

    server.newConnection.connect(on_second_launch)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
