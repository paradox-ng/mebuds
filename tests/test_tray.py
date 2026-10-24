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
