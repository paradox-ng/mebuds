"""About dialog, including the notices GPLv3 section 0 asks an interactive
program to show: copyright, no warranty, and where to find the license."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import __copyright__, __url__, __version__
from .icons import art_pixmap

LICENSE_URL = "https://www.gnu.org/licenses/gpl-3.0.html"


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("About mebuds")
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(art_pixmap("mebuds", 96, self.devicePixelRatioF()))
        top.addWidget(icon, 0, Qt.AlignTop)
        title = QLabel(
            f"<h2>mebuds {__version__}</h2>"
            "<p>Desktop application for controlling your Xiaomi earbuds, "
            "reverse engineered from the official Android app.</p>"
            f'<p>{__copyright__}<br><a href="{__url__}">{__url__}</a></p>'
        )
        title.setWordWrap(True)
        title.setOpenExternalLinks(True)
        top.addWidget(title, 1)
        layout.addLayout(top)

        legal = QLabel(
            "<p>This program is free software: you can redistribute it and/or "
            "modify it under the terms of the GNU General Public License as "
            "published by the Free Software Foundation, either version 3 of the "
            "License, or (at your option) any later version.</p>"
            "<p>It comes with ABSOLUTELY NO WARRANTY. See the "
            f'<a href="{LICENSE_URL}">GNU General Public License</a> for '
            "details.</p>"
            "<p>mebuds is not affiliated with or endorsed by Xiaomi.</p>"
        )
        legal.setWordWrap(True)
        legal.setOpenExternalLinks(True)
        layout.addWidget(legal)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        about_qt = QPushButton("About Qt")
        about_qt.clicked.connect(lambda: QMessageBox.aboutQt(self))
        buttons.addButton(about_qt, QDialogButtonBox.HelpRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setMinimumWidth(460)
