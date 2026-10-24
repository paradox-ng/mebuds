from mebuds.protocol import (
    OP_AUTH_CHECK,
    OP_GET_DEVICE_CONFIG,
    Config,
    Packet,
    StreamParser,
    decode_configs,
    encode_configs,
)

# Frames as sent and received on the wire.
AUTH_CHECK_CMD = bytes.fromhex(
    "fedcbac4500012000199c20c3ce2fb153f2c87bbd031e1f445ef"
)
GET_EQ_PRESET_RESP = bytes.fromhex("fedcba04f30006000903000707ef")
GET_UNSUPPORTED_RESP = bytes.fromhex("fedcba04f300020407ef")
BATTERY_PUSH = bytes.fromhex(
    "fedcbac70e000f0404" "00dfe49e020100020200020400ef"
)


def test_encode_command():
    p = Packet(OP_AUTH_CHECK, seq=0,
               data=bytes.fromhex("0199c20c3ce2fb153f2c87bbd031e1f445"))
    assert p.encode() == AUTH_CHECK_CMD


def test_decode_command_roundtrip():
    [p] = StreamParser().feed(AUTH_CHECK_CMD)
    assert p.is_command and p.expects_response and p.target == 4
    assert p.opcode == OP_AUTH_CHECK and p.seq == 0
    assert p.encode() == AUTH_CHECK_CMD


def test_decode_response_and_configs():
    [p] = StreamParser().feed(GET_EQ_PRESET_RESP)
    assert not p.is_command and p.status == 0 and p.seq == 9
    assert p.opcode == OP_GET_DEVICE_CONFIG
    assert decode_configs(p.data) == [Config(7, b"\x07")]


def test_unsupported_setting_status():
    [p] = StreamParser().feed(GET_UNSUPPORTED_RESP)
    assert p.status == 4 and p.data == b""


def test_split_and_concatenated_frames():
    stream = GET_EQ_PRESET_RESP + BATTERY_PUSH + GET_UNSUPPORTED_RESP
    parser = StreamParser()
    packets = []
    for i in range(0, len(stream), 5):
        packets += parser.feed(stream[i : i + 5])
    assert [p.opcode for p in packets] == [0xF3, 0x0E, 0xF3]


def test_garbage_before_frame_is_skipped():
    [p] = StreamParser().feed(b"\x00\xfe\xdc\x11" + GET_EQ_PRESET_RESP)
    assert p.seq == 9


def test_reply_echoes_device_seq():
    [push] = StreamParser().feed(BATTERY_PUSH)
    ack = Packet(push.opcode, is_command=False, expects_response=False,
                 seq=push.seq).encode()
    assert ack == bytes.fromhex("fedcba040e00020004ef")


def test_config_tlv_roundtrip():
    configs = [Config(2, bytes([4, 0xFF, 1])), Config(9, b"\x01\x03")]
    assert decode_configs(encode_configs(configs)) == configs
