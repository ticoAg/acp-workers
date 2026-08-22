from __future__ import annotations

import json
import os
from pathlib import Path

from typer.testing import CliRunner

from acpw.cli import app

runner = CliRunner()


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
