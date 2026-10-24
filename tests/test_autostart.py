import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="XDG autostart")


def test_autostart_entry(tmp_path, monkeypatch):
    from mebuds import autostart

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPIMAGE", "/opt/My Apps/mebuds.AppImage")
    assert not autostart.is_enabled()

    autostart.set_enabled(True, hidden=True)
    entry = (tmp_path / "autostart" / "mebuds.desktop").read_text()
    assert "Exec='/opt/My Apps/mebuds.AppImage' --hidden" in entry
    assert autostart.is_enabled() and autostart.starts_hidden()

    autostart.set_enabled(True, hidden=False)
    assert autostart.is_enabled() and not autostart.starts_hidden()

    autostart.set_enabled(False)
    assert not autostart.is_enabled()
