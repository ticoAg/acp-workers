from acpw.types import Adapter, ExecResponse, Registry, Worker, WorkerStatusList


def test_registry_roundtrip() -> None:
    data = Registry(workers={"grok": Worker(kind="grok", bind="127.0.0.1:48191")})
    restored = Registry.model_validate(data.model_dump())
    assert restored.workers["grok"].bind == "127.0.0.1:48191"


def test_exec_response_json() -> None:
    payload = ExecResponse(ok=True, name="mock", session_id="s", stop_reason="end_turn", text="pong")
    parsed = ExecResponse.model_validate_json(payload.model_dump_json())
    assert parsed.text == "pong"


def test_adapter_defaults() -> None:
    from acpw.adapters import ADAPTERS

    assert "grok" in ADAPTERS
    assert ADAPTERS["grok"].default_bind.endswith(":48191")
    assert isinstance(ADAPTERS["grok"], Adapter)
    dumped = WorkerStatusList(
        registry="/tmp/x",
        workers=[],
        listening_defaults=[],
        processes={},
    )
    assert dumped.ok is True
