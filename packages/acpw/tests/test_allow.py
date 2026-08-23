from __future__ import annotations

import json
import os
from pathlib import Path

from typer.testing import CliRunner

from acpw.cli import app
from acpw.registry import load_registry, save_registry

runner = CliRunner()


def _iso(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ACPW_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ACPW_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("ACPW_ALLOW", raising=False)
    os.chdir(tmp_path)


def test_allow_default_then_set_and_rm(tmp_path: Path, monkeypatch) -> None:
    _iso(tmp_path, monkeypatch)

    shown = runner.invoke(app, ["allow"])
    assert shown.exit_code == 0, shown.output
    body = json.loads(shown.output)
    assert body["source"] == "default"
    assert body["saved"] is None
    assert body["allow"] == ["claude", "codex", "cursor", "grok"]

    saved = runner.invoke(app, ["allow", "set", "grok", "cursor"])
    assert saved.exit_code == 0, saved.output
    body = json.loads(saved.output)
    assert body["source"] == "config"
    assert body["allow"] == ["cursor", "grok"]
    assert body["saved"] == ["cursor", "grok"]

    listed = json.loads(runner.invoke(app, ["ls"]).output)
    assert listed["allow"] == ["cursor", "grok"]
    assert listed["allow_source"] == "config"
    by_kind = {row["kind"]: row for row in listed["workers"]}
    assert by_kind["grok"]["allowed"] is True
    assert by_kind["cursor"]["allowed"] is True
    assert by_kind["claude"]["allowed"] is False
    assert by_kind["codex"]["allowed"] is False

    removed = runner.invoke(app, ["allow", "rm", "cursor"])
    assert json.loads(removed.output)["allow"] == ["grok"]

    added = runner.invoke(app, ["allow", "add", "cursor"])
    assert json.loads(added.output)["allow"] == ["cursor", "grok"]


def test_allow_rm_from_default_materializes_the_rest(tmp_path: Path, monkeypatch) -> None:
    _iso(tmp_path, monkeypatch)

    result = runner.invoke(app, ["allow", "rm", "claude"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["source"] == "config"
    assert "claude" not in body["allow"]
    assert set(body["allow"]) == {"codex", "cursor", "grok"}


def test_allow_accepts_registry_name_as_kind_alias(tmp_path: Path, monkeypatch) -> None:
    _iso(tmp_path, monkeypatch)
    added = runner.invoke(app, ["add", "claude-b", "--kind", "claude"])
    assert added.exit_code == 0, added.output

    result = runner.invoke(app, ["allow", "rm", "claude-b"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert "claude" not in body["allow"]


def test_allow_unknown_kind_fails(tmp_path: Path, monkeypatch) -> None:
    _iso(tmp_path, monkeypatch)
    result = runner.invoke(app, ["allow", "set", "no-such-kind"])
    assert result.exit_code == 1, result.output
    body = json.loads(result.output)
    assert body["ok"] is False
    assert "unknown kind" in body["error"]


def test_run_rejects_disallowed_kind(tmp_path: Path, monkeypatch) -> None:
    _iso(tmp_path, monkeypatch)

    set_ok = runner.invoke(app, ["allow", "set", "grok"])
    assert set_ok.exit_code == 0, set_ok.output

    result = runner.invoke(app, ["run", "claude", "-p", "nope"])
    assert result.exit_code == 1, result.output
    body = json.loads(result.output)
    assert body["ok"] is False
    assert "not allowed" in body["error"]
    assert "claude" in body["error"]


def test_disabled_registry_flag_still_blocks(tmp_path: Path, monkeypatch) -> None:
    _iso(tmp_path, monkeypatch)
    load_registry()
    data = load_registry()
    data.workers["grok"].enabled = False
    save_registry(data)

    result = runner.invoke(app, ["run", "grok", "-p", "nope"])
    assert result.exit_code == 1, result.output
    body = json.loads(result.output)
    assert "disabled" in body["error"]


def test_env_allow_overrides_config(tmp_path: Path, monkeypatch) -> None:
    _iso(tmp_path, monkeypatch)
    assert runner.invoke(app, ["allow", "set", "grok", "cursor"]).exit_code == 0
    monkeypatch.setenv("ACPW_ALLOW", "codex")

    body = json.loads(runner.invoke(app, ["allow"]).output)
    assert body["source"] == "env"
    assert body["allow"] == ["codex"]
    assert body["saved"] == ["cursor", "grok"]


def test_hidden_kind_stays_dispatchable(tmp_path: Path, monkeypatch) -> None:
    from acpw.allow import kind_allowed

    _iso(tmp_path, monkeypatch)
    assert runner.invoke(app, ["allow", "set", "grok"]).exit_code == 0
    assert kind_allowed("mock") is True
    assert kind_allowed("claude") is False
    assert kind_allowed("grok") is True
