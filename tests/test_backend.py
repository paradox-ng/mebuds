"""Platform backends: these mostly check that each one loads and behaves on
a machine without the earbuds (CI runners have no Bluetooth at all)."""

import sys
import uuid

import pytest


def test_watcher_scans_without_crashing(qapp):
    from mebuds.backend import make_watcher

    devices = make_watcher().scan()
    assert isinstance(devices, list)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows backend")
def test_windows_structures():
    import ctypes

    from mebuds import winbt

    assert ctypes.sizeof(winbt.SOCKADDR_BTH) == 30
    u = uuid.UUID("0000fd2d-0000-1000-8000-00805f9b34fb")
    assert winbt.GUID.from_uuid(u).to_uuid() == u
    assert winbt._address_str(winbt._address_int("12:34:56:78:9A:BC")) == (
        "12:34:56:78:9A:BC"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="Linux backend")
def test_python_has_bluetooth_sockets():
    # The Linux backend needs these; some prebuilt Pythons (including the
    # one actions/setup-python installs) are compiled without them.
    import socket

    assert hasattr(socket, "AF_BLUETOOTH")
    assert hasattr(socket, "BTPROTO_RFCOMM") and hasattr(socket, "BTPROTO_L2CAP")


def test_connect_error_is_reported_not_swallowed(qapp, monkeypatch):
    from mebuds import link as link_mod

    def boom(address):
        raise AttributeError("no AF_BLUETOOTH")

    monkeypatch.setattr(link_mod, "connect_control_channel", boom)
    results = []
    link = link_mod.Link()
    link._socketReady.disconnect()
    link._socketReady.connect(lambda sock, err: results.append((sock, err)))
    link._connect_worker("12:34:56:78:9A:BC")
    assert results == [(None, "no AF_BLUETOOTH")]


@pytest.mark.skipif(sys.platform == "win32", reason="Linux backend")
def test_sdp_parser_finds_rfcomm_channel():
    from mebuds import sdp

    # ProtocolDescriptorList: L2CAP, then RFCOMM channel 11.
    record = bytes.fromhex("3511" "090004" "350c" "3503190100" "3505190003" "080b")
    tree, _ = sdp._parse_element(record, 0)
    assert sdp._find_rfcomm_channel(tree) == 11


def test_app_window_builds(qapp):
    from mebuds.device import Buds
    from mebuds.window import ControlWindow

    w = ControlWindow(Buds())
    w.refresh()
    assert w.windowTitle() == "mebuds"
