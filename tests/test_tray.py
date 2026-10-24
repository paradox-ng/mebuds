from PySide6.QtCore import QObject, QSettings, Signal


class FakeWatcher(QObject):
    devicesChanged = Signal(list)

    def start(self):
        pass

    def rename(self, address, alias):
        return True


def make_app(qapp, tmp_path, monkeypatch):
    from mebuds import tray

    # Keep the user's real settings and earbuds out of the test.
    QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, str(tmp_path))
    monkeypatch.setattr(tray, "make_watcher", lambda: FakeWatcher())
    return tray.App(qapp, start_hidden=False)


def test_menu_hides_name_while_disconnected(qapp, tmp_path, monkeypatch):
    from mebuds.backend import BudsDevice

    app = make_app(qapp, tmp_path, monkeypatch)
    app.buds.connect_to = lambda address: None  # no real connection
    app._on_devices([BudsDevice("12:34:56:78:9A:BC", "PrdxBuds", connected=False)])
    app._update_tray()
    header = app.menu.actions()[0].text()
    assert header == "No earbuds connected"
    assert "PrdxBuds" not in app.tray.toolTip()
    assert app.window.title.text() == "No earbuds connected"
    app.window.hide()


def _connected(app):
    from mebuds import features as F
    from mebuds.device import Battery

    s = app.buds.state
    s.connection = "ready"
    s.name, s.vid, s.pid = "REDMI Buds 8 Active", 0x2717, 0x50E2
    s.model = F.model_for(s.vid, s.pid)
    s.left, s.case, s.right = Battery(95, False), Battery(57, True), Battery(100, False)
    s.configs[F.CFG_WEAR_STATE] = bytes([0x0C])


def test_status_for_the_command_line(qapp, tmp_path, monkeypatch):
    import json

    from mebuds.backend import BudsDevice

    app = make_app(qapp, tmp_path, monkeypatch)
    app.buds.connect_to = lambda address: None
    app._on_devices([BudsDevice("12:34:56:78:9A:BC", "PrdxBuds", connected=False)])
    assert app.status() == {
        "status": "disconnected", "connected": False, "text": "No earbuds connected",
    }

    app.device = BudsDevice("12:34:56:78:9A:BC", "PrdxBuds", connected=True)
    _connected(app)
    status = json.loads(json.dumps(app.status()))  # must be JSON-safe
    assert status["connected"] and status["name"] == "PrdxBuds"
    assert status["left"] == {"level": 95, "charging": False}
    assert status["case"] == {"level": 57, "charging": True}
    assert status["left_in_ear"] and status["right_in_ear"]
    assert status["text"] == "PrdxBuds: L 95%  ·  Case 57% ⚡  ·  R 100%"
    app.window.hide()


def test_connect_notification_once_per_connection(qapp, tmp_path, monkeypatch):
    app = make_app(qapp, tmp_path, monkeypatch)
    announced = []
    app._announce = lambda: announced.append(True)
    _connected(app)
    app._on_buds_changed()
    app._on_buds_changed()  # later updates don't repeat it
    assert announced == [True]
    app.buds.state.connection = "disconnected"
    app._on_buds_changed()
    _connected(app)
    app._on_buds_changed()
    assert announced == [True, True]
    app.window.hide()
