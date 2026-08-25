from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from acpw.cli import app
from acpw.paths import POOL_STATE_NAME, worker_state_dir
from acpw.pool import _init_params, _open_mux, pool_url

runner = CliRunner()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def isolate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ACPW_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ACPW_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ACPW_POOL_BIND", f"0.0.0.0:{free_port()}")
    os.chdir(tmp_path)


def register(name: str) -> None:
    added = runner.invoke(
        app, ["add", name, "--kind", "mock", "--bind", f"127.0.0.1:{free_port()}"]
    )
    assert added.exit_code == 0, added.output


def start_pool() -> None:
    up = runner.invoke(app, ["pool", "up"])
    assert up.exit_code == 0, up.output


def durable_map() -> dict:
    path = worker_state_dir(POOL_STATE_NAME) / "sessions.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def wait_unheld(client, session_id: str, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        listed = client.rpc("session/list", {}, timeout=20)
        row = next((item for item in listed["sessions"] if item["sessionId"] == session_id), None)
        if row is not None and not row["_meta"]["held"]:
            return
        time.sleep(0.05)
    raise AssertionError(f"session {session_id} still held")


def new_session(client, worker: str, cwd: Path) -> str:
    created = client.rpc(
        "session/new",
        {"cwd": str(cwd), "mcpServers": [], "_meta": {"worker": worker}},
        timeout=60,
    )
    sid = str(created["sessionId"])
    assert sid.startswith("acpw-s"), sid
    return sid


def test_session_list_empty_then_after_new(tmp_path: Path, monkeypatch) -> None:
    isolate(tmp_path, monkeypatch)
    register("alpha")
    start_pool()
    client = _open_mux(pool_url())
    try:
        init = client.rpc("initialize", _init_params(), timeout=20)
        caps = init["agentCapabilities"]["sessionCapabilities"]
        assert caps["list"] == {}
        assert caps["delete"] == {}
        empty = client.rpc("session/list", {}, timeout=20)
        assert empty == {"sessions": []}
        sid = new_session(client, "alpha", tmp_path)
        listed = client.rpc("session/list", {"sessionId": "ignore-me"}, timeout=20)
        assert "nextCursor" not in listed
        assert len(listed["sessions"]) == 1
        row = listed["sessions"][0]
        assert row["sessionId"] == sid
        assert row["cwd"] == str(tmp_path)
        assert row["_meta"] == {"worker": "alpha", "live": True, "held": True}
        blob = json.dumps(listed)
        assert "native" not in blob
        assert "mock-" not in blob
    finally:
        client.close()
        runner.invoke(app, ["pool", "down"])


def test_mux_list_sees_both_workers(tmp_path: Path, monkeypatch) -> None:
    isolate(tmp_path, monkeypatch)
    register("alpha")
    register("beta")
    start_pool()
    client = _open_mux(pool_url())
    try:
        client.rpc("initialize", _init_params(), timeout=20)
        sid_a = new_session(client, "alpha", tmp_path)
        sid_b = new_session(client, "beta", tmp_path)
        listed = client.rpc("session/list", {}, timeout=20)
        workers = {row["sessionId"]: row["_meta"]["worker"] for row in listed["sessions"]}
        assert workers[sid_a] == "alpha"
        assert workers[sid_b] == "beta"
        only_a = client.rpc("session/list", {"_meta": {"worker": "alpha"}}, timeout=20)
        assert [row["sessionId"] for row in only_a["sessions"]] == [sid_a]
    finally:
        client.close()
        runner.invoke(app, ["pool", "down"])


def test_session_delete_idempotent_then_unknown(tmp_path: Path, monkeypatch) -> None:
    isolate(tmp_path, monkeypatch)
    register("alpha")
    start_pool()
    client = _open_mux(pool_url())
    try:
        client.rpc("initialize", _init_params(), timeout=20)
        sid = new_session(client, "alpha", tmp_path)
        assert sid in durable_map()
        assert client.rpc("session/delete", {"sessionId": sid}, timeout=20) == {}
        assert client.rpc("session/delete", {"sessionId": sid}, timeout=20) == {}
        assert (
            client.rpc("session/delete", {"sessionId": "acpw-sdeadbeefdeadbeef"}, timeout=20) == {}
        )
        assert sid not in durable_map()
        with pytest.raises(RuntimeError, match="unknown session") as prompted:
            client.rpc(
                "session/prompt",
                {"sessionId": sid, "prompt": [{"type": "text", "text": "gone"}]},
                timeout=20,
            )
        assert "-32001" in str(prompted.value)
        with pytest.raises(RuntimeError, match="unknown session") as loaded:
            client.rpc(
                "session/load",
                {"sessionId": sid, "mcpServers": [], "_meta": {"worker": "alpha"}},
                timeout=20,
            )
        assert "-32001" in str(loaded.value)
        status = json.loads(runner.invoke(app, ["pool", "ls"]).output)
        assert any(row["name"] == "alpha" and row["alive"] for row in status["workers"])
    finally:
        client.close()
        runner.invoke(app, ["pool", "down"])


def test_delete_held_by_another_client(tmp_path: Path, monkeypatch) -> None:
    isolate(tmp_path, monkeypatch)
    register("alpha")
    start_pool()
    holder = _open_mux(pool_url())
    other = _open_mux(pool_url())
    try:
        holder.rpc("initialize", _init_params(), timeout=20)
        other.rpc("initialize", _init_params(), timeout=20)
        sid = new_session(holder, "alpha", tmp_path)
        with pytest.raises(RuntimeError, match="held by another client"):
            other.rpc("session/delete", {"sessionId": sid}, timeout=20)
        holder.close()
        wait_unheld(other, sid)
        assert other.rpc("session/delete", {"sessionId": sid}, timeout=20) == {}
        assert sid not in durable_map()
    finally:
        other.close()
        runner.invoke(app, ["pool", "down"])


def test_prune_does_not_delete_held_sessions(tmp_path: Path, monkeypatch) -> None:
    isolate(tmp_path, monkeypatch)
    register("alpha")
    start_pool()
    holder = _open_mux(pool_url())
    other = _open_mux(pool_url())
    try:
        holder.rpc("initialize", _init_params(), timeout=20)
        other.rpc("initialize", _init_params(), timeout=20)
        held_id = new_session(holder, "alpha", tmp_path)
        free_id = new_session(other, "alpha", tmp_path)
        other.close()
        wait_unheld(holder, free_id)
        pruned = runner.invoke(app, ["sessions", "prune"])
        assert pruned.exit_code == 0, pruned.output
        body = json.loads(pruned.output)
        assert body["deleted"] == 1
        assert body["kept"] == 1
        listed = holder.rpc("session/list", {}, timeout=20)
        ids = [row["sessionId"] for row in listed["sessions"]]
        assert ids == [held_id]
        assert free_id not in durable_map()
        assert held_id in durable_map()
        prompted = holder.rpc(
            "session/prompt",
            {"sessionId": held_id, "prompt": [{"type": "text", "text": "still-here"}]},
            timeout=30,
        )
        assert prompted["stopReason"] == "end_turn"
    finally:
        holder.close()
        runner.invoke(app, ["pool", "down"])


def test_unknown_method_still_no_route(tmp_path: Path, monkeypatch) -> None:
    isolate(tmp_path, monkeypatch)
    register("alpha")
    start_pool()
    client = _open_mux(pool_url())
    try:
        client.rpc("initialize", _init_params(), timeout=20)
        with pytest.raises(RuntimeError, match=r"no route: explode") as caught:
            client.rpc("explode", {}, timeout=10)
        assert "-32602" in str(caught.value)
        listed = client.rpc("session/list", {}, timeout=20)
        assert listed == {"sessions": []}
    finally:
        client.close()
        runner.invoke(app, ["pool", "down"])


def test_cli_sessions_list_rm(tmp_path: Path, monkeypatch) -> None:
    isolate(tmp_path, monkeypatch)
    register("alpha")
    start_pool()
    try:
        ran = runner.invoke(app, ["run", "alpha", "-p", "hi", "--cwd", str(tmp_path)])
        assert ran.exit_code == 0, ran.output
        sid = json.loads(ran.output)["session_id"]
        listed = runner.invoke(app, ["sessions"])
        assert listed.exit_code == 0, listed.output
        rows = json.loads(listed.output)["sessions"]
        assert rows[0]["session_id"] == sid
        assert rows[0]["worker"] == "alpha"
        assert rows[0]["cwd"] == str(tmp_path)
        assert rows[0]["live"] is True
        assert rows[0]["held"] is False
        again = runner.invoke(app, ["sessions", "list"])
        assert json.loads(again.output)["sessions"][0]["session_id"] == sid
        removed = runner.invoke(app, ["sessions", "rm", sid])
        assert removed.exit_code == 0, removed.output
        assert json.loads(removed.output)["session_id"] == sid
        empty = runner.invoke(app, ["sessions"])
        assert json.loads(empty.output)["sessions"] == []
    finally:
        runner.invoke(app, ["pool", "down"])
