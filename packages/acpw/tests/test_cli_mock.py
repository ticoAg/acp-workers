from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import pytest
from typer.testing import CliRunner

from acpw import __version__
from acpw.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _off_the_default_pool_port(monkeypatch):
    """`run` and `ping` start a pool on their own now, so keep it off 48190 and reap it."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    monkeypatch.setenv("ACPW_POOL_BIND", f"127.0.0.1:{port}")
    yield
    runner.invoke(app, ["pool", "down"])


def test_version_matches_package_metadata() -> None:
    for argv in (["version"], ["--version"]):
        result = runner.invoke(app, argv)
        assert result.exit_code == 0, result.output
        body = json.loads(result.output)
        assert body["ok"] is True
        assert body["version"] == __version__
        assert body["version"] != "0+unknown"


def test_selfcheck_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ACPW_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ACPW_STATE_DIR", str(tmp_path / "state"))
    os.chdir(tmp_path)

    result = runner.invoke(app, ["selfcheck"])
    body = json.loads(result.output)
    names = {item["name"]: item for item in body["checks"]}
    assert names["roundtrip"]["level"] == "ok", body
    assert names["cli"]["level"] == "ok", body
    assert body["failed"] == [], body
    assert result.exit_code == 0, result.output

    skipped = runner.invoke(app, ["selfcheck", "--no-live"])
    assert skipped.exit_code == 0, skipped.output
    body = json.loads(skipped.output)
    assert "roundtrip" in body["warned"]


def test_mock_lifecycle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ACPW_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ACPW_STATE_DIR", str(tmp_path / "state"))
    os.chdir(tmp_path)

    add = runner.invoke(app, ["add", "mock", "--kind", "mock", "--bind", "127.0.0.1:48199"])
    assert add.exit_code == 0, add.output
    assert json.loads(add.output)["saved"] == "mock"

    up = runner.invoke(app, ["up", "mock", "--cwd", str(tmp_path)])
    assert up.exit_code == 0, up.output
    body = json.loads(up.output)
    assert body["ok"] is True
    assert body["live"]["via"] == "health"

    try:
        ping = runner.invoke(app, ["ping", "mock"])
        assert ping.exit_code == 0, ping.output
        info = json.loads(ping.output)
        assert info["agent_info"]["name"] == "acpw-mock"

        ran = runner.invoke(app, ["run", "mock", "-p", "hello-task", "--cwd", str(tmp_path)])
        assert ran.exit_code == 0, ran.output
        result = json.loads(ran.output)
        assert result["ok"] is True
        assert result["text"] == "pong:hello-task"
        assert result["stop_reason"] == "end_turn"

        listed = runner.invoke(app, ["ls"])
        assert listed.exit_code == 0
        rows = json.loads(listed.output)["workers"]
        mock = next(row for row in rows if row["name"] == "mock")
        assert mock["live"] is True
    finally:
        down = runner.invoke(app, ["down", "mock"])
        assert down.exit_code == 0, down.output
