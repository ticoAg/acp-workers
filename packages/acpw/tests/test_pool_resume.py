"""A session is a conversation, not a socket: it has to survive the things that end sockets.

Three tiers, each losing more state than the last: the connection goes away (L1), the
agent process goes away (L2), the daemon itself goes away (L3). The public session id is
the only thing the host holds on to, and it has to keep working through all three.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from acpw.cli import app
from acpw.paths import POOL_STATE_NAME, registry_path, worker_state_dir
from acpw.pool import _init_params, _open_mux, pool_url

runner = CliRunner()

AGENTS = Path(__file__).parent / "agents"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def pool(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ACPW_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("ACPW_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ACPW_POOL_BIND", f"0.0.0.0:{free_port()}")
    os.chdir(tmp_path)
    yield tmp_path
    runner.invoke(app, ["pool", "down"])


def register(name: str, agent: str, *args: str) -> None:
    added = runner.invoke(
        app, ["add", name, "--kind", "mock", "--bind", f"127.0.0.1:{free_port()}"]
    )
    assert added.exit_code == 0, added.output
    path = registry_path()
    registry = json.loads(path.read_text())
    registry["workers"][name]["stdio_argv"] = [sys.executable, str(AGENTS / agent), *args]
    path.write_text(json.dumps(registry))


def pool_up() -> None:
    up = runner.invoke(app, ["pool", "up", "--bind", os.environ["ACPW_POOL_BIND"]])
    assert up.exit_code == 0, up.output


def say(session_id: str | None, worker: str, text: str, cwd: Path) -> tuple[str, str]:
    """One turn on its own connection, the way the CLI does it. Returns (id, transcript)."""
    client = _open_mux(pool_url())
    try:
        client.rpc("initialize", _init_params(), timeout=20)
        if session_id is None:
            created = client.rpc(
                "session/new",
                {"cwd": str(cwd), "mcpServers": [], "_meta": {"worker": worker}},
                timeout=60,
            )
            session_id = str(created["sessionId"])
        client.rpc(
            "session/prompt",
            {"sessionId": session_id, "prompt": [{"type": "text", "text": text}]},
            timeout=60,
        )
        chunks = [
            u["update"]["content"]["text"]
            for u in client.updates(session_id)
            if u["update"].get("sessionUpdate") == "agent_message_chunk"
        ]
        return session_id, chunks[-1] if chunks else ""
    finally:
        client.close()


def test_a_new_connection_resumes_the_conversation(pool: Path) -> None:
    register("keeper", "resume_agent.py", str(pool / "store.json"), "keeper")
    pool_up()

    session_id, first = say(None, "keeper", "one", pool)
    assert first == "hist:one"

    # Same id, a connection that never saw the first turn.
    _, second = say(session_id, "keeper", "two", pool)
    assert second == "hist:one|two", "the agent lost the history across connections"


def test_a_killed_child_is_respawned_and_reloaded(pool: Path) -> None:
    register("keeper", "resume_agent.py", str(pool / "store.json"), "keeper")
    pool_up()
    session_id, _ = say(None, "keeper", "one", pool)

    status = json.loads(runner.invoke(app, ["pool", "ls"]).output)
    child_pid = next(w["pid"] for w in status["workers"] if w["name"] == "keeper")
    os.kill(child_pid, signal.SIGKILL)
    for _ in range(40):
        status = json.loads(runner.invoke(app, ["pool", "ls"]).output)
        if not any(w["name"] == "keeper" and w["alive"] for w in status["workers"]):
            break
        time.sleep(0.1)

    _, text = say(session_id, "keeper", "two", pool)
    assert text == "hist:one|two", "history did not survive the agent process"

    after = json.loads(runner.invoke(app, ["pool", "ls"]).output)
    fresh = next(w["pid"] for w in after["workers"] if w["name"] == "keeper")
    assert fresh != child_pid, "expected a new child process"


def test_the_session_map_survives_a_daemon_restart(pool: Path) -> None:
    register("keeper", "resume_agent.py", str(pool / "store.json"), "keeper")
    pool_up()
    session_id, _ = say(None, "keeper", "one", pool)

    down = runner.invoke(app, ["pool", "down"])
    assert json.loads(down.output)["live"] is False
    assert (worker_state_dir(POOL_STATE_NAME) / "sessions.json").is_file()

    pool_up()
    _, text = say(session_id, "keeper", "two", pool)
    assert text == "hist:one|two", "the daemon forgot the session across a restart"


def test_an_agent_that_cannot_resume_says_so(pool: Path) -> None:
    # perm_agent has no loadSession capability, so tier 2 must refuse rather than guess.
    register("mute", "perm_agent.py", "mute")
    pool_up()

    client = _open_mux(pool_url())
    try:
        client.rpc("initialize", _init_params(), timeout=20)
        created = client.rpc(
            "session/new",
            {"cwd": str(pool), "mcpServers": [], "_meta": {"worker": "mute"}},
            timeout=60,
        )
        session_id = str(created["sessionId"])
    finally:
        client.close()

    stopped = runner.invoke(app, ["pool", "ls"])
    assert stopped.exit_code == 0
    client = _open_mux(pool_url())
    try:
        client.rpc("initialize", _init_params(), timeout=20)
        client.rpc("worker/down", {"name": "mute"}, timeout=20)
        with pytest.raises(RuntimeError) as caught:
            client.rpc(
                "session/prompt",
                {"sessionId": session_id, "prompt": [{"type": "text", "text": "again"}]},
                timeout=30,
            )
        assert "cannot resume sessions (loadSession not advertised)" in str(caught.value)
    finally:
        client.close()


def test_an_unknown_session_id_is_refused(pool: Path) -> None:
    register("keeper", "resume_agent.py", str(pool / "store.json"), "keeper")
    pool_up()

    client = _open_mux(pool_url())
    try:
        client.rpc("initialize", _init_params(), timeout=20)
        with pytest.raises(RuntimeError) as caught:
            client.rpc(
                "session/prompt",
                {
                    "sessionId": "acpw-sdeadbeefdeadbeef",
                    "prompt": [{"type": "text", "text": "hello"}],
                },
                timeout=30,
            )
        assert "unknown session" in str(caught.value)
    finally:
        client.close()
