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


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


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
    assert any(row["name"] == "mock" and row["alive"] for row in body["workers"])

    try:
        ping = runner.invoke(app, ["ping", "mock"])
        assert ping.exit_code == 0, ping.output
        info = json.loads(ping.output)
        assert info["ok"] is True

        ran = runner.invoke(app, ["run", "mock", "-p", "hello-task", "--cwd", str(tmp_path)])
        assert ran.exit_code == 0, ran.output
        result = json.loads(ran.output)
        assert result["ok"] is True
        assert result["text"] == "pong:hello-task"
        assert result["stop_reason"] == "end_turn"
        assert result["session_id"]

        again = runner.invoke(
            app,
            [
                "run",
                "mock",
                "-p",
                "again",
                "--cwd",
                str(tmp_path),
                "--session-id",
                result["session_id"],
            ],
        )
        # The in-package mock does not advertise loadSession, but L1 keeps the
        # session attached while the child is still warm.
        assert again.exit_code == 0, again.output
        assert json.loads(again.output)["session_id"] == result["session_id"]

        listed = runner.invoke(app, ["ls"])
        assert listed.exit_code == 0
        listing = json.loads(listed.output)
        assert listing["pool"]["live"] is True
        mock = next(row for row in listing["workers"] if row["name"] == "mock")
        assert mock["live"] is True
        assert mock["via"] == "pool"
    finally:
        down = runner.invoke(app, ["down"])
        assert down.exit_code == 0, down.output


def test_one_socket_owns_many_agents_and_resumes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ACPW_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ACPW_STATE_DIR", str(tmp_path / "state"))
    os.chdir(tmp_path)

    for name in ("alpha", "beta"):
        added = runner.invoke(
            app, ["add", name, "--kind", "mock", "--bind", f"127.0.0.1:{_free_port()}"]
        )
        assert added.exit_code == 0, added.output

    up = runner.invoke(app, ["up", "--cwd", str(tmp_path)])
    assert up.exit_code == 0, up.output
    started = json.loads(up.output)
    assert started["ok"] is True
    assert started["workers"] == []

    try:
        first = runner.invoke(app, ["run", "alpha", "-p", "a1", "--cwd", str(tmp_path)])
        second = runner.invoke(app, ["run", "beta", "-p", "b1", "--cwd", str(tmp_path)])
        assert first.exit_code == 0, first.output
        assert second.exit_code == 0, second.output
        alpha = json.loads(first.output)
        beta = json.loads(second.output)
        assert alpha["text"] == "pong:a1"
        assert beta["text"] == "pong:b1"
        assert alpha["session_id"] != beta["session_id"]

        resumed = runner.invoke(
            app,
            [
                "run",
                "alpha",
                "-p",
                "a2",
                "--cwd",
                str(tmp_path),
                "--session-id",
                alpha["session_id"],
            ],
        )
        assert resumed.exit_code == 0, resumed.output
        assert json.loads(resumed.output)["session_id"] == alpha["session_id"]

        listed = json.loads(runner.invoke(app, ["ls"]).output)
        assert listed["pool"]["live"] is True
        by_name = {row["name"]: row for row in listed["workers"]}
        assert by_name["alpha"]["via"] == "pool"
        assert by_name["beta"]["via"] == "pool"

        stopped = runner.invoke(app, ["down", "alpha"])
        assert stopped.exit_code == 0, stopped.output
        after = json.loads(runner.invoke(app, ["ls"]).output)
        assert after["pool"]["live"] is True
        rows = {row["name"]: row for row in after["workers"]}
        assert rows["alpha"]["via"] != "pool"
        assert rows["beta"]["via"] == "pool"
    finally:
        down = runner.invoke(app, ["down"])
        assert down.exit_code == 0, down.output
        assert json.loads(down.output)["live"] is False


def test_no_pool_is_the_standalone_escape_hatch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ACPW_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ACPW_STATE_DIR", str(tmp_path / "state"))
    os.chdir(tmp_path)

    add = runner.invoke(app, ["add", "mock", "--kind", "mock", "--bind", "127.0.0.1:48199"])
    assert add.exit_code == 0, add.output

    up = runner.invoke(app, ["up", "mock", "--no-pool", "--cwd", str(tmp_path)])
    assert up.exit_code == 0, up.output
    body = json.loads(up.output)
    assert body["ok"] is True
    assert body["live"]["via"] == "health"
    try:
        listed = json.loads(runner.invoke(app, ["ls"]).output)
        mock = next(row for row in listed["workers"] if row["name"] == "mock")
        assert mock["via"] == "gateway"
        assert listed["pool"]["live"] is False
    finally:
        down = runner.invoke(app, ["down", "mock", "--no-pool"])
        assert down.exit_code == 0, down.output
