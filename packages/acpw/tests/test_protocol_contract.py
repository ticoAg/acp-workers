from pathlib import Path

from acpw.daemon import initialize_result

ROOT = Path(__file__).resolve().parents[3]
PROTOCOL = ROOT / "docs" / "pool-protocol.md"


def test_pool_protocol_keeps_code_names() -> None:
    text = PROTOCOL.read_text(encoding="utf-8")
    for needle in (
        "session/new",
        "_meta.worker",
        "worker/list",
        "session/list",
        "session/delete",
    ):
        assert needle in text, needle


def test_initialize_result_advertises_session_list_and_delete() -> None:
    caps = initialize_result()["agentCapabilities"]
    assert caps["loadSession"] is True
    assert caps["sessionCapabilities"] == {"list": {}, "delete": {}}
    assert caps["promptCapabilities"]["embeddedContext"] is True
