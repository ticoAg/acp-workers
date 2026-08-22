from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

from typer.main import get_command
from typer.testing import CliRunner

from acpw.cli import app
from acpw.locales import ZH_CN, ZH_TW

runner = CliRunner()
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text: str) -> str:
    return ANSI.sub("", text)


def test_catalogs_have_the_same_keys() -> None:
    assert set(ZH_CN) == set(ZH_TW)


def test_cli_help_is_in_the_catalogs() -> None:
    missing: list[str] = []

    def walk(cmd: object) -> None:
        help_text = getattr(cmd, "help", None)
        if isinstance(help_text, str) and help_text.strip():
            key = inspect.cleandoc(help_text)
            if key not in ZH_CN:
                missing.append(key)
        for param in getattr(cmd, "params", []):
            param_help = getattr(param, "help", None)
            if isinstance(param_help, str) and param_help.strip() and param_help not in ZH_CN:
                missing.append(param_help)
        commands = getattr(cmd, "commands", None)
        if commands:
            for child in commands.values():
                walk(child)

    walk(get_command(app))
    assert missing == [], missing


def test_root_help_zh_cn() -> None:
    result = runner.invoke(app, ["--lang", "zh-CN", "--help"])
    assert result.exit_code == 0, result.output
    text = _plain(result.output)
    assert "用法:" in text
    assert "一条 WebSocket" in text
    assert "选项" in text
    assert "命令" in text
    assert "显示本帮助并退出" in text
    assert "查看或保存 CLI 语言" in text


def test_root_help_zh_tw() -> None:
    result = runner.invoke(app, ["--lang", "zh-TW", "--help"])
    assert result.exit_code == 0, result.output
    text = _plain(result.output)
    assert "用法:" in text
    assert "一條 WebSocket" in text
    assert "選項" in text
    assert "顯示本說明並結束" in text


def test_root_help_en_us() -> None:
    result = runner.invoke(app, ["--lang", "en-US", "--help"])
    assert result.exit_code == 0, result.output
    text = _plain(result.output)
    assert "Usage:" in text
    assert "One WebSocket, many agents" in text
    assert "Options" in text
    assert "Show this message and exit." in text


def test_run_help_is_complete_in_zh_cn() -> None:
    result = runner.invoke(app, ["run", "--help", "--lang", "zh-CN"])
    assert result.exit_code == 0, result.output
    text = _plain(result.output)
    assert "派发一条 prompt" in text
    assert "续这个 session" in text
    assert "从该文件读取 prompt" in text
    assert "要派发的 worker" in text


def test_missing_argument_prompt_zh_cn() -> None:
    result = runner.invoke(app, ["--lang", "zh-CN", "ping"])
    assert result.exit_code == 2
    text = _plain(result.output)
    assert "缺少参数" in text
    assert "试试" in text
    assert "错误" in text


def test_empty_prompt_error_follows_lang() -> None:
    result = runner.invoke(app, ["--lang", "zh-TW", "run", "mock", "-p", "  "])
    assert result.exit_code == 1
    body = json.loads(result.output)
    assert body["ok"] is False
    assert body["error"] == "prompt 為空"


def test_unknown_worker_follows_lang(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ACPW_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ACPW_STATE_DIR", str(tmp_path / "state"))
    result = runner.invoke(app, ["--lang", "zh-CN", "rm", "no-such-worker"])
    assert result.exit_code == 1
    body = json.loads(result.output)
    assert body["error"] == "未知 worker no-such-worker"


def test_lang_get_and_set(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ACPW_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ACPW_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("ACPW_LANG", raising=False)

    shown = runner.invoke(app, ["lang"])
    assert shown.exit_code == 0, shown.output
    body = json.loads(shown.output)
    assert body["ok"] is True
    assert body["lang"] == "en-US"
    assert body["supported"] == ["en-US", "zh-CN", "zh-TW"]

    again = runner.invoke(app, ["lang", "get"])
    assert again.exit_code == 0, again.output
    assert json.loads(again.output)["lang"] == "en-US"

    saved = runner.invoke(app, ["lang", "set", "zh"])
    assert saved.exit_code == 0, saved.output
    body = json.loads(saved.output)
    assert body["lang"] == "zh-CN"
    assert body["saved"] == "zh-CN"
    assert body["source"] == "config"

    help_result = runner.invoke(app, ["--help"])
    assert "一条 WebSocket" in _plain(help_result.output)

    listed = runner.invoke(app, ["--lang", "zh-CN", "lang", "--help"])
    text = _plain(listed.output)
    assert "保存 CLI 语言" in text
    assert "打印当前 CLI 语言" in text

    bad = runner.invoke(app, ["lang", "set", "fr-FR"])
    assert bad.exit_code == 1
    err = json.loads(bad.output)
    assert err["ok"] is False
    assert "fr-FR" in err["error"]
    assert err["known"] == ["en-US", "zh-CN", "zh-TW"]


def test_acpw_lang_env(monkeypatch) -> None:
    monkeypatch.setenv("ACPW_LANG", "zh-TW")
    result = runner.invoke(app, ["--help"])
    assert "一條 WebSocket" in _plain(result.output)


def test_invalid_lang_flag_is_json() -> None:
    result = runner.invoke(app, ["--lang", "nope", "--help"])
    assert result.exit_code == 1
    body = json.loads(result.output)
    assert body["ok"] is False
    assert "nope" in body["error"]
    assert body["known"] == ["en-US", "zh-CN", "zh-TW"]


def test_version_json_stays_english_under_zh() -> None:
    result = runner.invoke(app, ["--lang", "zh-CN", "version"])
    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["ok"] is True
    assert "version" in body
    assert "python" in body
    assert "location" in body
