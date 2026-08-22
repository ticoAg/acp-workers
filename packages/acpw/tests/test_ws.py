from __future__ import annotations

from acpw.ws import ws_frame


def test_client_control_frames_are_masked() -> None:
    pong = ws_frame(0xA, b"ping", client=True)
    close = ws_frame(0x8, b"", client=True)
    assert pong[0] & 0x0F == 0xA
    assert pong[1] & 0x80
    assert close[0] & 0x0F == 0x8
    assert close[1] & 0x80


def test_server_control_frames_are_unmasked() -> None:
    pong = ws_frame(0xA, b"ping", client=False)
    assert pong[0] & 0x0F == 0xA
    assert pong[1] & 0x80 == 0
    assert pong[2:] == b"ping"
