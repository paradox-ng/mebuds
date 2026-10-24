"""The control window. Sections appear only for features the connected model
has."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import autostart
from . import features as F
from .about import AboutDialog
from .device import Battery, Buds, BudsState
from .icons import app_icon, art_pixmap, battery_pixmap

EQ_SEND_DELAY_MS = 300

CONNECTION_TEXT = {
    "connecting": "Connecting…",
    "authenticating": "Connecting…",
    "ready": "Connected",
}


def _freq_label(hz: int) -> str:
    return f"{hz // 1000}K" if hz >= 1000 and hz % 1000 == 0 else (
        f"{hz / 1000:g}K" if hz >= 1000 else str(hz)
    )


class BatteryCard(QFrame):
    ART_SIZE = 72

    def __init__(self, title: str, art: str, mirror: bool = False):
        super().__init__()
        self.art, self.mirror = art, mirror
        self.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignHCenter)
        self.picture = QLabel(alignment=Qt.AlignHCenter)
        self.icon = QLabel()
        self.level = QLabel("–")
        font = self.level.font()
        font.setPointSizeF(font.pointSizeF() * 1.4)
        self.level.setFont(font)
        level_row = QHBoxLayout()
        level_row.addStretch()
        level_row.addWidget(self.icon)
        level_row.addWidget(self.level)
        level_row.addStretch()
        self.title = QLabel(title, alignment=Qt.AlignHCenter)
        self.status = QLabel("", alignment=Qt.AlignHCenter)
        self.status.setEnabled(False)
        layout.addWidget(self.picture)
        layout.addLayout(level_row)
        layout.addWidget(self.title)
        layout.addWidget(self.status)

    def set_battery(self, b: Battery, status: str = ""):
        dpr = self.devicePixelRatioF()
        self.picture.setPixmap(
            art_pixmap(self.art, self.ART_SIZE, dpr, self.mirror, dimmed=b.level is None)
        )
        self.icon.setPixmap(battery_pixmap(b.level, b.charging, 22, dpr))
        if b.level is None:
            self.level.setText("–")
        else:
            self.level.setText(f"{b.level}%")
        self.icon.setToolTip("Charging" if b.charging else "")
        self.status.setText(status)


class EqualizerEditor(QWidget):
    """Vertical sliders, one per band. Dragging previews on the buds; letting
    go saves the curve."""

    preview = Signal(object)
    save = Signal(object)

    def __init__(self):
        super().__init__()
        self._eq: F.CustomEq | None = None
        self._sliders: list[QSlider] = []
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self.preview.emit(self.current()))

    def set_eq(self, eq: F.CustomEq | None):
        if eq is None:
            return
        same_shape = self._eq is not None and [f for f, _ in self._eq.bands] == [
            f for f, _ in eq.bands
        ]
        self._eq = eq
        if not same_shape:
            self._rebuild()
        for slider, (_, gain) in zip(self._sliders, eq.bands):
            if not slider.isSliderDown():
                slider.blockSignals(True)
                slider.setValue(gain)
                slider.blockSignals(False)
                slider.setToolTip(f"{gain:+d} dB")

    def _rebuild(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._sliders = []
        eq = self._eq
        self._grid.addWidget(QLabel(f"+{eq.max_gain} dB"), 0, 0, Qt.AlignRight | Qt.AlignTop)
        self._grid.addWidget(QLabel(f"−{eq.min_gain} dB"), 0, 0, Qt.AlignRight | Qt.AlignBottom)
        for col, (freq, _) in enumerate(eq.bands, start=1):
            s = QSlider(Qt.Vertical)
            s.setRange(-eq.min_gain, eq.max_gain)
            s.setTickPosition(QSlider.TicksBothSides)
            s.setTickInterval(eq.max_gain)
            s.setMinimumHeight(140)
            s.valueChanged.connect(self._on_change)
            s.sliderReleased.connect(lambda: self.save.emit(self.current()))
            self._grid.addWidget(s, 0, col, Qt.AlignHCenter)
            self._grid.addWidget(QLabel(_freq_label(freq)), 1, col, Qt.AlignHCenter)
            self._sliders.append(s)

    def _on_change(self, value: int):
        slider = self.sender()
        slider.setToolTip(f"{value:+d} dB")
        if slider.isSliderDown():
            self._timer.start(EQ_SEND_DELAY_MS)
        else:  # keyboard / wheel: no release event, save directly
            self.save.emit(self.current())

    def current(self) -> F.CustomEq:
        bands = [(f, s.value()) for (f, _), s in zip(self._eq.bands, self._sliders)]
        return F.CustomEq(self._eq.max_gain, self._eq.min_gain, bands)

    def reset(self):
        for s in self._sliders:
            s.blockSignals(True)
            s.setValue(0)
            s.blockSignals(False)
        self.save.emit(self.current())


class ControlWindow(QWidget):
    renameRequested = Signal(str)
    trayVisibilityChanged = Signal(bool)
    lowBatteryNotifyChanged = Signal(bool)
    quitRequested = Signal()

    def __init__(self, buds: Buds):
        super().__init__()
        self.buds = buds
        self.tray_available = True
        self.setWindowTitle("mebuds")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(520)

        root = QVBoxLayout(self)

        # --- header ---
        self.title = QLabel("No earbuds")
        font = self.title.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() * 1.3)
        self.title.setFont(font)
        self.status = QLabel("")
        self.status.setEnabled(False)
        header = QHBoxLayout()
        header.addWidget(self.title)
        header.addStretch()
        header.addWidget(self.status)
        root.addLayout(header)

        # --- batteries ---
        # The drawing is the right earbud; the left one is its mirror image.
        self.left_card = BatteryCard("Left", "earbud", mirror=True)
        self.case_card = BatteryCard("Case", "case")
        self.right_card = BatteryCard("Right", "earbud")
        cards = QHBoxLayout()
        for c in (self.left_card, self.case_card, self.right_card):
            cards.addWidget(c)
        root.addLayout(cards)

        # --- tabs ---
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        self._build_sound_tab()
        self._build_gestures_tab()
        self._build_device_tab()
        self._build_settings_tab()

        buds.changed.connect(self.refresh)
        self.refresh()

    # ----- tabs -----
    def _build_sound_tab(self):
        self.sound_tab = QWidget()
        layout = QVBoxLayout(self.sound_tab)
        row = QHBoxLayout()
        row.addWidget(QLabel("Audio balance"))
        self.eq_combo = QComboBox()
        self.eq_combo.activated.connect(self._on_eq_preset)
        row.addWidget(self.eq_combo, 1)
        layout.addLayout(row)

        self.eq_box = QWidget()
        eq_layout = QVBoxLayout(self.eq_box)
        eq_layout.setContentsMargins(0, 8, 0, 0)
        eq_header = QHBoxLayout()
        eq_header.addWidget(QLabel("Equalizer"))
        eq_header.addStretch()
        reset = QPushButton("Reset")
        eq_header.addWidget(reset)
        eq_layout.addLayout(eq_header)
        self.eq_editor = EqualizerEditor()
        self.eq_editor.preview.connect(self.buds.preview_custom_eq)
        self.eq_editor.save.connect(self.buds.save_custom_eq)
        reset.clicked.connect(self.eq_editor.reset)
        eq_layout.addWidget(self.eq_editor)
        layout.addWidget(self.eq_box)
        hint = QLabel("Play some music while choosing, to hear the difference.")
        hint.setEnabled(False)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch()
        self.tabs.addTab(self.sound_tab, "Sound")

    def _build_gestures_tab(self):
        self.gestures_tab = QWidget()
        self.gestures_grid = QGridLayout(self.gestures_tab)
        self.gestures_grid.addWidget(QLabel("<b>Left</b>"), 0, 1, Qt.AlignHCenter)
        self.gestures_grid.addWidget(QLabel("<b>Right</b>"), 0, 2, Qt.AlignHCenter)
        self.gesture_combos: dict[tuple[int, str], QComboBox] = {}
        self._gesture_model: F.Model | None = None
        self.tabs.addTab(self.gestures_tab, "Gestures")

    def _rebuild_gestures(self, model: F.Model):
        for combo in self.gesture_combos.values():
            combo.deleteLater()
        for i in reversed(range(self.gestures_grid.count())):
            item = self.gestures_grid.itemAt(i)
            row, _, _, _ = self.gestures_grid.getItemPosition(i)
            if row > 0 and item.widget():
                item.widget().deleteLater()
        self.gesture_combos = {}
        row = 1
        order = (F.GESTURE_SINGLE_TAP, F.GESTURE_DOUBLE_TAP, F.GESTURE_TRIPLE_TAP,
                 F.GESTURE_LONG_PRESS, F.GESTURE_SLIDE)
        for gesture in order:
            actions = model.gestures.get(gesture)
            if not actions:
                continue
            self.gestures_grid.addWidget(QLabel(F.GESTURE_NAMES[gesture]), row, 0)
            for col, side in ((1, "left"), (2, "right")):
                combo = QComboBox()
                for a in actions:
                    combo.addItem(F.ACTION_NAMES.get(a, f"Action {a}"), a)
                combo.activated.connect(
                    lambda _i, g=gesture, s=side, c=combo: self.buds.set_gesture(
                        g, s, c.currentData()
                    )
                )
                self.gestures_grid.addWidget(combo, row, col)
                self.gesture_combos[(gesture, side)] = combo
            row += 1
        note = QLabel("Single-tap gestures are easy to trigger by accident.")
        note.setEnabled(False)
        self.gestures_grid.addWidget(note, row, 0, 1, 3)
        self.gestures_grid.setRowStretch(row + 1, 1)
        self._gesture_model = model

    def _build_device_tab(self):
        self.device_tab = QWidget()
        layout = QVBoxLayout(self.device_tab)

        self.dual_check = QCheckBox("Dual connection")
        self.dual_check.setToolTip("Connect the earbuds to two devices at the same time")
        self.dual_check.toggled.connect(
            lambda on: self.buds.set_flag(F.CFG_DUAL_CONNECTION, on)
        )
        layout.addWidget(self.dual_check)

        self.find_box = QWidget()
        find = QVBoxLayout(self.find_box)
        find.setContentsMargins(0, 8, 0, 0)
        find.addWidget(QLabel("<b>Find your earbuds</b>"))
        warn = QLabel(
            "The alarm is loud. Don't play it while the earbuds are in your ears."
        )
        warn.setWordWrap(True)
        warn.setEnabled(False)
        find.addWidget(warn)
        buttons = QHBoxLayout()
        for text, side in (("Left", F.SIDE_LEFT), ("Both", F.SIDE_BOTH),
                           ("Right", F.SIDE_RIGHT)):
            b = QPushButton(f"Ring {text.lower()}")
            b.clicked.connect(lambda _=False, s=side: self.buds.find_buds(True, s))
            buttons.addWidget(b)
        stop = QPushButton("Stop")
        stop.clicked.connect(lambda: self.buds.find_buds(False))
        buttons.addWidget(stop)
        find.addLayout(buttons)
        layout.addWidget(self.find_box)

        info_title = QLabel("<b>About</b>")
        info_title.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(info_title)
        form = QFormLayout()
        self.info_name = QLabel()
        rename = QPushButton("Rename…")
        rename.clicked.connect(self._on_rename)
        name_row = QHBoxLayout()
        name_row.addWidget(self.info_name, 1)
        name_row.addWidget(rename)
        form.addRow("Name", name_row)
        self.info_model = QLabel()
        self.info_address = QLabel()
        self.info_firmware = QLabel()
        self.info_serial = QLabel()
        for label, w in (("Model", self.info_model), ("MAC address", self.info_address),
                         ("Firmware", self.info_firmware), ("Serial no.", self.info_serial)):
            w.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(label, w)
        layout.addLayout(form)
        layout.addStretch()
        self.tabs.addTab(self.device_tab, "Device")

    def _build_settings_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.tray_check = QCheckBox("Show tray icon")
        self.tray_check.toggled.connect(self.trayVisibilityChanged)
        self.lowbat_check = QCheckBox("Notify when an earbud's battery is low")
        self.lowbat_check.toggled.connect(self.lowBatteryNotifyChanged)
        layout.addWidget(self.tray_check)
        layout.addWidget(self.lowbat_check)

        self.autostart_check = QCheckBox("Start mebuds when you log in")
        self.autostart_hidden_check = QCheckBox("Start in the tray, without opening the window")
        self.autostart_hidden_check.setContentsMargins(24, 0, 0, 0)
        hidden_row = QHBoxLayout()
        hidden_row.setContentsMargins(24, 0, 0, 0)
        hidden_row.addWidget(self.autostart_hidden_check)
        self.autostart_check.setChecked(autostart.is_enabled())
        self.autostart_hidden_check.setChecked(autostart.starts_hidden())
        self.autostart_hidden_check.setEnabled(self.autostart_check.isChecked())
        self.autostart_check.toggled.connect(self._on_autostart)
        self.autostart_hidden_check.toggled.connect(self._on_autostart)
        layout.addWidget(self.autostart_check)
        layout.addLayout(hidden_row)

        layout.addStretch()
        about = QPushButton("About mebuds")
        about.clicked.connect(self.show_about)
        about_row = QHBoxLayout()
        about_row.addStretch()
        about_row.addWidget(about)
        layout.addLayout(about_row)
        self.tabs.addTab(tab, "Settings")

    def show_about(self):
        AboutDialog(self).exec()

    def _on_autostart(self):
        enabled = self.autostart_check.isChecked()
        self.autostart_hidden_check.setEnabled(enabled)
        try:
            autostart.set_enabled(enabled, self.autostart_hidden_check.isChecked())
        except OSError as exc:
            QMessageBox.warning(self, "Autostart", f"Couldn't change autostart:\n{exc}")

    # ----- state -> widgets -----
    def set_settings(self, tray_visible: bool, tray_supported: bool, low_battery: bool):
        for w, v in ((self.tray_check, tray_visible), (self.lowbat_check, low_battery)):
            w.blockSignals(True)
            w.setChecked(v)
            w.blockSignals(False)
        self.tray_check.setEnabled(tray_supported)
        if not tray_supported:
            self.tray_check.setToolTip("No system tray found on this desktop")

    def refresh(self):
        s: BudsState = self.buds.state
        model = s.model
        self.title.setText((s.alias or s.name or model.name) if s.address else "No earbuds")
        if s.ready:
            self.status.setText("Connected")
        elif s.connection in CONNECTION_TEXT:
            self.status.setText(CONNECTION_TEXT[s.connection])
        elif s.error:
            self.status.setText("Not connected")
        else:
            self.status.setText("Disconnected" if s.address else "")
        self.status.setToolTip(s.error)

        wear = s.wear()
        unknown = Battery()
        self.left_card.set_battery(
            s.left if s.ready else unknown,
            self._where(wear["left_in_ear"], wear["left_in_case"], s),
        )
        self.right_card.set_battery(
            s.right if s.ready else unknown,
            self._where(wear["right_in_ear"], wear["right_in_case"], s),
        )
        # The buds only know the case's charge while one of them sits in it.
        self.case_card.set_battery(
            s.case if s.ready else unknown,
            "" if s.case.level is not None or not s.ready else "Put a bud in to read",
        )

        # Sound
        has_sound = bool(model.eq_presets)
        self.tabs.setTabVisible(self.tabs.indexOf(self.sound_tab), has_sound)
        if has_sound:
            current = s.byte(F.CFG_EQ_PRESET)
            if [self.eq_combo.itemData(i) for i in range(self.eq_combo.count())] != list(model.eq_presets):
                self.eq_combo.clear()
                for p in model.eq_presets:
                    self.eq_combo.addItem(F.EQ_PRESET_NAMES.get(p, f"Preset {p}"), p)
            idx = self.eq_combo.findData(current)
            self.eq_combo.setCurrentIndex(idx)
            custom = model.custom_eq and current == F.EQ_CUSTOM
            self.eq_box.setVisible(custom)
            if custom:
                self.eq_editor.set_eq(s.custom_eq())

        # Gestures
        has_gestures = bool(model.gestures)
        self.tabs.setTabVisible(self.tabs.indexOf(self.gestures_tab), has_gestures)
        if has_gestures:
            if self._gesture_model is not model:
                self._rebuild_gestures(model)
            for gesture, (left, right) in s.gestures().items():
                for side, action in (("left", left), ("right", right)):
                    combo = self.gesture_combos.get((gesture, side))
                    if combo is None:
                        continue
                    i = combo.findData(action)
                    if i < 0:  # set to something the official app doesn't offer
                        combo.addItem(F.ACTION_NAMES.get(action, f"Action {action}"), action)
                        i = combo.count() - 1
                    combo.setCurrentIndex(i)

        # Device
        self.dual_check.setVisible(model.dual_connection)
        dual = s.flag(F.CFG_DUAL_CONNECTION)
        self.dual_check.blockSignals(True)
        self.dual_check.setChecked(bool(dual))
        self.dual_check.blockSignals(False)
        self.find_box.setVisible(model.find_buds)
        self.info_name.setText(s.alias or s.name or "–")
        if model is F.UNKNOWN_MODEL:
            pid = f" (PID {s.pid:04X})" if s.pid is not None else ""
            self.info_model.setText(f"Unknown{pid}")
        else:
            self.info_model.setText(f"{model.name} ({model.code})" if model.code else model.name)
        self.info_address.setText(s.address or "–")
        self.info_firmware.setText(s.firmware or "–")
        self.info_serial.setText(s.serial or "–")

        for tab in range(self.tabs.count() - 1):  # settings stay usable
            self.tabs.widget(tab).setEnabled(s.ready)

    @staticmethod
    def _where(in_ear: bool, in_case: bool, s: BudsState) -> str:
        if not s.ready or F.CFG_WEAR_STATE not in s.configs:
            return ""
        if in_case:
            return "In case"
        return "In ear" if in_ear else "Out"

    # ----- actions -----
    def _on_eq_preset(self, index: int):
        self.buds.set_eq_preset(self.eq_combo.itemData(index))

    def _on_rename(self):
        current = self.buds.state.alias or self.buds.state.name
        name, ok = QInputDialog.getText(self, "Rename earbuds", "Name:", text=current)
        if ok and name.strip() and name.strip() != current:
            self.renameRequested.emit(name.strip())

    def closeEvent(self, event):
        if self.tray_available:
            event.ignore()
            self.hide()
        else:
            event.accept()
            self.quitRequested.emit()
