"""Vectors captured from a real REDMI Buds 8 Active, which accepted them."""

from mebuds import auth


def test_device_answer_to_our_challenge():
    challenge = bytes.fromhex("99c20c3ce2fb153f2c87bbd031e1f445")
    assert auth.encrypted_auth_check_data(challenge).hex() == (
        "40ea1a88b014b5d05745e621b8edfef2"
    )


def test_our_answer_to_device_challenge():
    challenge = bytes.fromhex("555cb3e92621154cd11fe9d6965b5905")
    assert auth.encrypted_auth_check_data(challenge).hex() == (
        "40f4cd12f264e2b19f57b34f64ce57a0"
    )


def test_matches_native_library_on_zero_input():
    # Output of the official app's libxm_bluetooth.so, run under emulation.
    assert auth.e21(bytes(16)).hex() == "bca5905bc849392e7bf9fdcdc570ef77"


def test_raw_handshake_shape():
    challenge = auth.random_auth_data()
    assert len(challenge) == 17 and challenge[0] == 0
    answer = auth.encrypted_auth_data(challenge)
    assert answer[0] == 1 and answer[1:] == auth.e21(challenge[1:])
