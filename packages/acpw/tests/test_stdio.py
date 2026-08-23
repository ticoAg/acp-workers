from __future__ import annotations

import json
import os
import re
import select
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from acpw.cli import app
from acpw.paths import registry_path
from acpw.pool import _init_params, _open_mux, pool_url

runner = CliRunner()
PUBLIC_SESSION = re.compile(r"^acpw-s[0-9a-f]{16}$")
PERM_AGENT = Path(__file__).parent / "agents" / "perm_agent.py"


def free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def isolate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ACPW_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ACPW_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ACPW_POOL_BIND", f"127.0.0.1:{free_port()}")
    os.chdir(tmp_path)


def register(name: str) -> None:
    added = runner.invoke(
        app, ["add", name, "--kind", "mock", "--bind", f"127.0.0.1:{free_port()}"]
    )
    assert added.exit_code == 0, added.output


def reap(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)


class StdioAgent:
    def __init__(self, name: str) -> None:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "acpw", "stdio", name],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            bufsize=0,
        )
        assert self.proc.stdin and self.proc.stdout and self.proc.stderr
        self._n = 0

    def close(self) -> None:
        if self.proc.stdin and not self.proc.stdin.closed:
            try:
                self.proc.stdin.close()
            except OSError:
                pass
        reap(self.proc)

    def send(self, obj: dict[str, Any]) -> None:
        assert self.proc.stdin
        self.proc.stdin.write((json.dumps(obj, ensure_ascii=False) + "\n").encode())
        self.proc.stdin.flush()

    def recv(self, timeout: float = 20.0) -> dict[str, Any]:
        assert self.proc.stdout
        deadline = time.time() + timeout
        while time.time() < deadline:
            ready, _, _ = select.select(
                [self.proc.stdout], [], [], max(0.05, deadline - time.time())
            )
            if not ready:
                break
            line = self.proc.stdout.readline()
            if not line:
                err = self.proc.stderr.read().decode("utf-8", "replace") if self.proc.stderr else ""
                raise ConnectionError(f"stdio closed rc={self.proc.poll()} stderr={err}")
            text = line.decode("utf-8", "replace").strip()
            if text:
                obj = json.loads(text)
                if isinstance(obj, dict):
                    return obj
        raise TimeoutError("timed out waiting for ACP frame")

    def rpc(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float = 30.0,
        on_request: Any = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        self._n += 1
        msg_id = self._n
        self.send({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}})
        notes: list[dict[str, Any]] = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            obj = self.recv(timeout=max(0.1, deadline - time.time()))
            if obj.get("method") and obj.get("id") is not None:
                if on_request is None:
                    raise AssertionError(f"unexpected inbound request {obj}")
                reply = on_request(obj)
                if reply is not None:
                    self.send(reply)
                continue
            if obj.get("id") == msg_id:
                return obj, notes
            notes.append(obj)
        raise TimeoutError(f"timed out waiting for {method}")


def initialize(agent: StdioAgent) -> dict[str, Any]:
    reply, _notes = agent.rpc("initialize", _init_params())
    assert "error" not in reply, reply
    result = reply["result"]
    assert result["protocolVersion"] == 1
    assert result["agentCapabilities"]["loadSession"] is True
    return result


def test_stdio_opens_a_session_without_meta_worker(tmp_path: Path, monkeypatch) -> None:
    isolate(tmp_path, monkeypatch)
    register("alpha")
    agent = StdioAgent("alpha")
    try:
        info = initialize(agent)
        assert info["agentInfo"]["name"] == "acpw/alpha"

        created, _ = agent.rpc(
            "session/new",
            {"cwd": str(tmp_path), "mcpServers": []},
        )
        assert "error" not in created, created
        session_id = created["result"]["sessionId"]
        assert PUBLIC_SESSION.match(session_id), session_id

        prompted, notes = agent.rpc(
            "session/prompt",
            {"sessionId": session_id, "prompt": [{"type": "text", "text": "hello"}]},
        )
        assert prompted.get("result", {}).get("stopReason") == "end_turn", prompted
        text = "".join(
            note["params"]["update"]["content"]["text"]
            for note in notes
            if note.get("method") == "session/update"
            and note.get("params", {}).get("update", {}).get("sessionUpdate")
            == "agent_message_chunk"
        )
        assert text == "pong:hello", (text, notes)
    finally:
        agent.close()
        runner.invoke(app, ["pool", "down"])


def test_mux_still_requires_meta_worker(tmp_path: Path, monkeypatch) -> None:
    isolate(tmp_path, monkeypatch)
    register("alpha")
    up = runner.invoke(app, ["pool", "up"])
    assert up.exit_code == 0, up.output
    client = _open_mux(pool_url())
    try:
        client.rpc("initialize", _init_params(), timeout=20)
        with pytest.raises(RuntimeError, match="missing _meta.worker"):
            client.rpc(
                "session/new",
                {"cwd": str(tmp_path), "mcpServers": []},
                timeout=20,
            )
    finally:
        client.close()
        runner.invoke(app, ["pool", "down"])


def test_stdio_rejects_worker_methods(tmp_path: Path, monkeypatch) -> None:
    isolate(tmp_path, monkeypatch)
    register("alpha")
    agent = StdioAgent("alpha")
    try:
        initialize(agent)
        reply, _ = agent.rpc("worker/up", {"name": "alpha"})
        assert reply["error"]["code"] == -32601, reply
        listed = json.loads(runner.invoke(app, ["pool", "ls"]).output)
        assert listed["workers"] == [] or all(not row["alive"] for row in listed["workers"])
    finally:
        agent.close()
        runner.invoke(app, ["pool", "down"])


def test_permission_request_reaches_stdio(tmp_path: Path, monkeypatch) -> None:
    isolate(tmp_path, monkeypatch)
    register("asker")
    registry_file = registry_path()
    registry = json.loads(registry_file.read_text())
    registry["workers"]["asker"]["stdio_argv"] = [sys.executable, str(PERM_AGENT), "asker"]
    registry_file.write_text(json.dumps(registry))

    agent = StdioAgent("asker")
    inbound: dict[str, Any] = {}

    def on_request(obj: dict[str, Any]) -> dict[str, Any]:
        inbound.update(obj)
        assert obj["method"] == "session/request_permission"
        assert str(obj["id"]).startswith("acpw:")
        return {
            "jsonrpc": "2.0",
            "id": obj["id"],
            "result": {"outcome": {"outcome": "selected", "optionId": "allow-once"}},
        }

    try:
        initialize(agent)
        created, _ = agent.rpc("session/new", {"cwd": str(tmp_path), "mcpServers": []})
        session_id = created["result"]["sessionId"]
        prompted, notes = agent.rpc(
            "session/prompt",
            {"sessionId": session_id, "prompt": [{"type": "text", "text": "please"}]},
            on_request=on_request,
        )
        assert prompted.get("result", {}).get("stopReason") == "end_turn", prompted
        assert inbound, "child request never reached stdio"
        text = "".join(
            note["params"]["update"]["content"]["text"]
            for note in notes
            if note.get("method") == "session/update"
            and note.get("params", {}).get("update", {}).get("sessionUpdate")
            == "agent_message_chunk"
        )
        assert "allow-once" in text, (text, notes)
    finally:
        agent.close()
        runner.invoke(app, ["pool", "down"])


def test_stdio_eof_releases_session_for_run(tmp_path: Path, monkeypatch) -> None:
    isolate(tmp_path, monkeypatch)
    register("alpha")
    agent = StdioAgent("alpha")
    try:
        initialize(agent)
        created, _ = agent.rpc("session/new", {"cwd": str(tmp_path), "mcpServers": []})
        session_id = created["result"]["sessionId"]
        agent.rpc(
            "session/prompt",
            {"sessionId": session_id, "prompt": [{"type": "text", "text": "one"}]},
        )
    finally:
        if agent.proc.stdin and not agent.proc.stdin.closed:
            agent.proc.stdin.close()
        rc = agent.proc.wait(timeout=8)
        assert rc == 0, (
            agent.proc.stderr.read().decode("utf-8", "replace") if agent.proc.stderr else rc
        )

    try:
        resumed = runner.invoke(
            app, ["run", "alpha", "-p", "two", "--cwd", str(tmp_path), "--session-id", session_id]
        )
        assert resumed.exit_code == 0, resumed.output
        assert json.loads(resumed.output)["text"] == "pong:two"
    finally:
        runner.invoke(app, ["pool", "down"])


def test_stdio_unknown_worker_writes_nothing_to_stdout(tmp_path: Path, monkeypatch) -> None:
    isolate(tmp_path, monkeypatch)
    proc = subprocess.Popen(
        [sys.executable, "-m", "acpw", "stdio", "nope"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=os.environ.copy(),
    )
    stdout, stderr = proc.communicate(timeout=10)
    assert proc.returncode == 1
    assert stdout == b""
    err = stderr.decode("utf-8", "replace")
    assert "unknown worker" in err or "未知 worker" in err


def test_stdio_respects_allow_list(tmp_path: Path, monkeypatch) -> None:
    isolate(tmp_path, monkeypatch)
    set_allow = runner.invoke(app, ["allow", "set", "cursor"])
    assert set_allow.exit_code == 0, set_allow.output
    proc = subprocess.Popen(
        [sys.executable, "-m", "acpw", "stdio", "grok"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=os.environ.copy(),
    )
    stdout, stderr = proc.communicate(timeout=10)
    assert proc.returncode == 1
    assert stdout == b""
    err = stderr.decode("utf-8", "replace")
    assert "not allowed" in err or "不在允许" in err or "不在允許" in err


def test_stdio_rejects_url_only_worker_without_url(tmp_path: Path, monkeypatch) -> None:
    isolate(tmp_path, monkeypatch)
    added = runner.invoke(
        app, ["add", "remote", "--kind", "remote", "--url", "ws://127.0.0.1:9/ws?server-key=x"]
    )
    assert added.exit_code == 0, added.output
    proc = subprocess.Popen(
        [sys.executable, "-m", "acpw", "stdio", "remote"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=os.environ.copy(),
    )
    stdout, stderr = proc.communicate(timeout=10)
    assert proc.returncode == 1
    assert stdout == b""
    err = stderr.decode("utf-8", "replace")
    assert "no stdio adapter" in err or "没有 stdio" in err or "沒有 stdio" in err


def test_two_mux_connections_two_workers(tmp_path: Path, monkeypatch) -> None:
    isolate(tmp_path, monkeypatch)
    register("alpha")
    register("beta")
    up = runner.invoke(app, ["pool", "up"])
    assert up.exit_code == 0, up.output
    left = _open_mux(pool_url())
    right = _open_mux(pool_url())
    try:
        left.rpc("initialize", _init_params(), timeout=20)
        right.rpc("initialize", _init_params(), timeout=20)
        sid_a = left.rpc(
            "session/new",
            {"cwd": str(tmp_path), "mcpServers": [], "_meta": {"worker": "alpha"}},
            timeout=60,
        )["sessionId"]
        sid_b = right.rpc(
            "session/new",
            {"cwd": str(tmp_path), "mcpServers": [], "_meta": {"worker": "beta"}},
            timeout=60,
        )["sessionId"]
        assert (
            left.rpc(
                "session/prompt",
                {"sessionId": sid_a, "prompt": [{"type": "text", "text": "from-alpha"}]},
                timeout=30,
            )["stopReason"]
            == "end_turn"
        )
        assert (
            right.rpc(
                "session/prompt",
                {"sessionId": sid_b, "prompt": [{"type": "text", "text": "from-beta"}]},
                timeout=30,
            )["stopReason"]
            == "end_turn"
        )
    finally:
        left.close()
        right.close()
        runner.invoke(app, ["pool", "down"])


def test_two_stdio_processes_stay_on_their_workers(tmp_path: Path, monkeypatch) -> None:
    isolate(tmp_path, monkeypatch)
    register("alpha")
    register("beta")
    up = runner.invoke(app, ["pool", "up"])
    assert up.exit_code == 0, up.output
    left = StdioAgent("alpha")
    right = StdioAgent("beta")
    try:
        initialize(left)
        initialize(right)
        a, _ = left.rpc("session/new", {"cwd": str(tmp_path), "mcpServers": []})
        b, _ = right.rpc("session/new", {"cwd": str(tmp_path), "mcpServers": []})
        assert "error" not in a, a
        assert "error" not in b, b
        sid_a, sid_b = a["result"]["sessionId"], b["result"]["sessionId"]
        assert sid_a != sid_b

        prompted_a, notes_a = left.rpc(
            "session/prompt",
            {"sessionId": sid_a, "prompt": [{"type": "text", "text": "from-alpha"}]},
        )
        try:
            prompted_b, notes_b = right.rpc(
                "session/prompt",
                {"sessionId": sid_b, "prompt": [{"type": "text", "text": "from-beta"}]},
            )
        except TimeoutError:
            log = Path(os.environ["ACPW_STATE_DIR"]) / "_pool" / "server.log"
            detail = log.read_text() if log.exists() else ""
            raise AssertionError(
                f"right hung poll={right.proc.poll()} sid={sid_a!r}/{sid_b!r}\n{detail[-3000:]}"
            ) from None
        assert prompted_a["result"]["stopReason"] == "end_turn"
        assert prompted_b["result"]["stopReason"] == "end_turn"

        def chunk_text(notes: list[dict[str, Any]]) -> str:
            return "".join(
                note["params"]["update"]["content"]["text"]
                for note in notes
                if note.get("method") == "session/update"
                and note.get("params", {}).get("update", {}).get("sessionUpdate")
                == "agent_message_chunk"
            )

        assert chunk_text(notes_a) == "pong:from-alpha"
        assert chunk_text(notes_b) == "pong:from-beta"
    finally:
        left.close()
        right.close()
        runner.invoke(app, ["pool", "down"])
