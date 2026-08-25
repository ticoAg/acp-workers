from __future__ import annotations

import json
import re
from pathlib import Path

from typer.testing import CliRunner

from acpw.cli import app
from acpw.output import OutputState, apply, dumps, render
from acpw.types import (
    CheckItem,
    CheckLevel,
    DoctorAdapter,
    DoctorResponse,
    ErrorResponse,
    ExecResponse,
    PoolStatus,
    PoolWorker,
    SelfCheckResponse,
    SessionInfo,
    SessionListResponse,
    ToolCallOut,
    VersionResponse,
    WorkerStatus,
    WorkerStatusList,
)

runner = CliRunner()


def _markdown() -> None:
    apply(OutputState(format="markdown", source="default", saved=None))


def _json() -> None:
    apply(OutputState(format="json", source="flag", saved=None))


def test_render_sessions_is_a_table() -> None:
    _markdown()
    body = render(
        SessionListResponse(
            sessions=[
                SessionInfo(
                    session_id="acpw-s0123456789abcdef",
                    worker="grok",
                    cwd="/tmp/work",
                    live=True,
                    held=False,
                )
            ]
        )
    )
    assert body.startswith("ok\n")
    assert "| session_id | worker | cwd | live | held |" in body
    assert "| acpw-s0123456789abcdef | grok | `/tmp/work` | true | false |" in body


def test_render_doctor_is_a_table() -> None:
    body = render(
        DoctorResponse(
            adapters=[
                DoctorAdapter(
                    kind="grok",
                    transport="native-ws",
                    binary="grok",
                    path="/home/tico/.local/bin/grok",
                    present=True,
                    default_bind="0.0.0.0:48191",
                )
            ],
            python="/opt/python",
        )
    )
    assert body.startswith("ok\n")
    assert "## adapters" in body
    assert "| kind | transport | binary | path | present | default_bind |" in body
    assert (
        "| grok | native-ws | grok | `/home/tico/.local/bin/grok` | true | 0.0.0.0:48191 |" in body
    )
    assert "python: `/opt/python`" in body
    assert "{" not in body


def test_render_ls_puts_pool_first() -> None:
    body = render(
        WorkerStatusList(
            registry="/home/tico/.config/acp-workers/registry.json",
            workers=[
                WorkerStatus(
                    name="grok",
                    kind="grok",
                    enabled=True,
                    transport="native-ws",
                    bind="0.0.0.0:48191",
                    live=True,
                    probe="pool",
                    pid=1937088,
                    url="ws://127.0.0.1:48191/ws",
                    manual_url=False,
                    via="pool",
                ),
                WorkerStatus(
                    name="claude",
                    kind="claude",
                    enabled=True,
                    transport="stdio-bridge",
                    bind="0.0.0.0:48192",
                    live=False,
                    probe=None,
                    pid=None,
                    url="ws://127.0.0.1:48192/ws",
                    manual_url=False,
                    via=None,
                ),
            ],
            listening_defaults=[],
            processes={"grok": [], "claude": []},
            pool=PoolStatus(
                live=True,
                bind="0.0.0.0:48190",
                url="ws://127.0.0.1:48190/ws?server-key=secret",
                pid=1937078,
                workers=[PoolWorker(name="grok", kind="grok", alive=True, pid=1937088, sessions=2)],
                sessions=2,
                log="/home/tico/.local/state/acp-workers/_pool/server.log",
            ),
        )
    )
    pool_at = body.index("## pool")
    workers_at = body.index("## workers")
    assert pool_at < workers_at
    assert "live: true" in body
    assert "listening_defaults" not in body
    assert "## processes" not in body
    assert "registry: `/home/tico/.config/acp-workers/registry.json`" in body
    assert "| grok | grok | true | true | native-ws |" in body
    assert "via" in body.split("## workers", 1)[1]


def test_render_exec_puts_agent_text_after_meta() -> None:
    body = render(
        ExecResponse(
            ok=True,
            name="grok",
            session_id="acpw-s0123456789abcdef",
            stop_reason="end_turn",
            text="## done\n\npatched cli.py",
            tool_calls=[
                ToolCallOut(kind="tool_call", title="edit", status="completed", name="edit")
            ],
        )
    )
    meta, _, text = body.partition("\n---\n\n")
    assert meta.startswith("ok\n")
    assert "session_id: acpw-s0123456789abcdef" in meta
    assert "stop_reason: end_turn" in meta
    assert "## tool_calls" in meta
    assert text == "## done\n\npatched cli.py"


def test_render_error_and_selfcheck() -> None:
    err = render(ErrorResponse(error="unknown worker no-such-worker", name="no-such-worker"))
    assert err.splitlines()[0] == "ok: false"
    assert "error: unknown worker no-such-worker" in err
    assert "name: no-such-worker" in err

    check = render(
        SelfCheckResponse(
            ok=False,
            version="0.6.3",
            checks=[
                CheckItem(name="cli", level=CheckLevel.ok, detail="acpw 0.6.3"),
                CheckItem(name="roundtrip", level=CheckLevel.fail, detail="timeout"),
            ],
            warned=["exposure"],
            failed=["roundtrip"],
        )
    )
    assert check.startswith("ok: false\n")
    failed_at = check.index("failed: roundtrip")
    checks_at = check.index("## checks")
    assert failed_at < checks_at
    assert "warned: exposure" in check


def test_dumps_json_is_one_line() -> None:
    _json()
    payload = VersionResponse(version="0.6.3", python="3.12.3", location="/opt/acpw")
    text = dumps(payload)
    assert json.loads(text)["version"] == "0.6.3"
    assert "\n" not in text
    _markdown()
    md = dumps(payload)
    assert md.startswith("ok\n")
    assert "version: 0.6.3" in md


def test_cli_defaults_to_markdown(monkeypatch) -> None:
    monkeypatch.delenv("ACPW_OUTPUT", raising=False)
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("ok\n")
    assert "version:" in result.output
    assert result.output.strip()[0] != "{"


def test_cli_json_flag_and_position(monkeypatch) -> None:
    monkeypatch.delenv("ACPW_OUTPUT", raising=False)
    for argv in (["--json", "version"], ["version", "--json"], ["--format", "json", "doctor"]):
        result = runner.invoke(app, argv)
        assert result.exit_code == 0, result.output
        body = json.loads(result.output)
        assert body["ok"] is True


def test_flag_beats_env(monkeypatch) -> None:
    monkeypatch.setenv("ACPW_OUTPUT", "json")
    result = runner.invoke(app, ["--format", "markdown", "version"])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("ok\n")
    assert result.output.strip()[0] != "{"


def test_config_output_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ACPW_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ACPW_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("ACPW_OUTPUT", raising=False)
    saved = runner.invoke(app, ["output", "set", "json"])
    assert saved.exit_code == 0, saved.output
    body = json.loads(saved.output)
    assert body["output"] == "json"
    assert body["source"] == "config"
    again = runner.invoke(app, ["version"])
    assert json.loads(again.output)["ok"] is True


def test_output_get_and_invalid(monkeypatch) -> None:
    monkeypatch.delenv("ACPW_OUTPUT", raising=False)
    shown = runner.invoke(app, ["output"])
    assert shown.exit_code == 0, shown.output
    assert "output: markdown" in shown.output
    bad = runner.invoke(app, ["output", "set", "xml"])
    assert bad.exit_code == 1
    assert "ok: false" in bad.output
    assert "xml" in bad.output
    flag = runner.invoke(app, ["--format", "nope", "version"])
    assert flag.exit_code == 1
    assert "ok: false" in flag.output


def test_markdown_error_keeps_translated_message(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ACPW_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ACPW_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("ACPW_OUTPUT", raising=False)
    result = runner.invoke(app, ["--lang", "zh-CN", "rm", "no-such-worker"])
    assert result.exit_code == 1
    assert "ok: false" in result.output
    assert "未知 worker no-such-worker" in result.output


def test_version_line_is_sed_friendly(monkeypatch) -> None:
    monkeypatch.delenv("ACPW_OUTPUT", raising=False)
    result = runner.invoke(app, ["version"])
    match = re.search(r"^version:\s*(.+)$", result.output, re.MULTILINE)
    assert match is not None
    assert match.group(1).strip()
