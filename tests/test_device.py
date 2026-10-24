from mebuds import features as F
from mebuds.device import Battery, Buds
from mebuds.protocol import StreamParser

TARGET_INFO = bytes.fromhex(
    "fedcba0402004b00021400"
    "5245444d49204275647320382041637469766505013065306505032717"
    "50e20204010205000306306504075f64ff020801020900020c00020d01"
    "020e000910100164 64ff003065".replace(" ", "")
    + "ef"
)
BATTERY_PUSH = bytes.fromhex("fedcbac70e000f040400dfe49e020100020200020400ef")
WEAR_PUSH = bytes.fromhex("fedcbac7f40005060300 0c03ef".replace(" ", ""))


def _feed(buds, frame):
    [p] = StreamParser().feed(frame)
    return p


def test_battery_byte():
    assert Battery.parse(0xDF) == Battery(95, True)
    assert Battery.parse(0x64) == Battery(100, False)
    assert Battery.parse(0xFF) == Battery(None, False)


def test_target_info(qapp):
    buds = Buds()
    buds.link.request = lambda *a, **k: None  # no device behind this
    buds._on_target_info(_feed(buds, TARGET_INFO))
    s = buds.state
    assert s.name == "REDMI Buds 8 Active"
    assert (s.vid, s.pid) == (0x2717, 0x50E2)
    assert s.model.code == "M2537E1"
    assert s.firmware == "3.0.6.5"
    assert s.left == Battery(95, False)
    assert s.right == Battery(100, False)
    assert s.case == Battery(None, False)


def test_battery_push_is_acknowledged(qapp):
    buds = Buds()
    replies = []
    buds.link.reply = lambda p, data=b"", status=0: replies.append((p.opcode, status))
    buds._on_push(_feed(buds, BATTERY_PUSH))
    assert buds.state.left == Battery(95, True)
    assert buds.state.right == Battery(100, True)
    assert buds.state.case == Battery(30, True)
    assert replies == [(0x0E, 0)]


def test_disconnect_forgets_battery_and_settings(qapp):
    buds = Buds()
    buds.link.reply = lambda *a, **k: None
    buds._on_push(_feed(buds, BATTERY_PUSH))
    buds._on_push(_feed(buds, WEAR_PUSH))
    buds.state.name = "REDMI Buds 8 Active"
    buds._on_link_state("disconnected")
    s = buds.state
    assert (s.left, s.right, s.case) == (Battery(), Battery(), Battery())
    assert s.configs == {}
    assert s.name == "REDMI Buds 8 Active"


def test_window_hides_battery_while_disconnected(qapp):
    from mebuds.window import ControlWindow

    buds = Buds()
    buds.state.address = "12:34:56:78:9A:BC"
    buds.state.left = Battery(100, True)  # stale value from before
    buds.state.alias = "PrdxBuds"
    w = ControlWindow(buds)
    w.refresh()
    assert w.left_card.level.text() == "–"
    assert w.info_name.text() == "–"


def test_wear_state_push(qapp):
    buds = Buds()
    buds.link.reply = lambda *a, **k: None
    buds._on_push(_feed(buds, WEAR_PUSH))
    assert buds.state.wear() == {
        "left_in_ear": False,
        "right_in_ear": False,
        "left_in_case": True,
        "right_in_case": True,
    }


def test_unknown_model_shows_only_basics():
    model = F.model_for(0x2717, 0x1234)
    assert model is F.UNKNOWN_MODEL
    assert not model.gestures and not model.eq_presets


def test_custom_eq_parse_and_save():
    raw = bytes.fromhex(
        "010a060600000a003e00007d0000fa0001f40003e80007d0000fa0001f40002ee0003e8000"
    )
    eq = F.CustomEq.parse(raw)
    assert (eq.max_gain, eq.min_gain, len(eq.bands)) == (6, 6, 10)
    assert eq.bands[0] == (62, 0) and eq.bands[-1] == (16000, 0)
    eq.bands[0] = (62, -3)
    assert eq.save_value()[:7] == bytes([1, 10, 1, 1, 1, 0, 10])
    assert eq.save_value()[7:10] == bytes([0, 62, 0x83])
