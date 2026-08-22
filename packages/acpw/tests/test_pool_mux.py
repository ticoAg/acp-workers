from __future__ import annotations

import json
import os
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from typer.testing import CliRunner

from acpw.cli import app
from acpw.paths import registry_path
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


def test_pool_drives_two_children_over_one_connection(tmp_path: Path, monkeypatch) -> None:
    isolate(tmp_path, monkeypatch)
    register("alpha")
    register("beta")

    bind = os.environ["ACPW_POOL_BIND"]
    up = runner.invoke(app, ["pool", "up", "--bind", bind, "--worker", "alpha", "--worker", "beta"])
    assert up.exit_code == 0, up.output
    started = json.loads(up.output)
    assert started["already"] is False
    assert {worker["name"] for worker in started["workers"]} == {"alpha", "beta"}

    try:
        listed = runner.invoke(app, ["pool", "ls"])
        assert listed.exit_code == 0, listed.output
        status = json.loads(listed.output)
        assert status["live"] is True
        children = {worker["name"]: worker for worker in status["workers"]}
        assert children["alpha"]["alive"] and children["beta"]["alive"]
        # Two adapters, two processes, one port.
        assert children["alpha"]["pid"] != children["beta"]["pid"]

        client = _open_mux(pool_url())
        try:
            client.rpc("initialize", _init_params(), timeout=20)

            def session_for(worker: str) -> str:
                created = client.rpc(
                    "session/new",
                    {
                        "cwd": str(tmp_path),
                        "mcpServers": [],
                        "_meta": {"worker": worker, "yoloMode": True},
                    },
                    timeout=60,
                )
                return str(created["sessionId"])

            sessions = {worker: session_for(worker) for worker in ("alpha", "beta")}
            assert sessions["alpha"] != sessions["beta"]

            def prompt(worker: str) -> dict:
                return client.rpc(
                    "session/prompt",
                    {
                        "sessionId": sessions[worker],
                        "prompt": [{"type": "text", "text": f"task-{worker}"}],
                    },
                    timeout=60,
                )

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(prompt, ["alpha", "beta"]))
            assert all(result["stopReason"] == "end_turn" for result in results), results

            # Each answer came back on its own session, so the id remapping held.
            for worker, session_id in sessions.items():
                updates = client.updates(session_id)
                text = "".join(
                    update["update"]["content"]["text"]
                    for update in updates
                    if update["update"].get("sessionUpdate") == "agent_message_chunk"
                )
                assert text == f"pong:task-{worker}", (worker, text, updates)
        finally:
            client.close()
    finally:
        down = runner.invoke(app, ["pool", "down"])
        assert down.exit_code == 0, down.output
        assert json.loads(down.output)["live"] is False


def test_session_ids_do_not_cross_connections(tmp_path: Path, monkeypatch) -> None:
    isolate(tmp_path, monkeypatch)
    register("alpha")

    bind = os.environ["ACPW_POOL_BIND"]
    up = runner.invoke(app, ["pool", "up", "--bind", bind])
    assert up.exit_code == 0, up.output

    try:
        owner = _open_mux(pool_url())
        intruder = _open_mux(pool_url())
        try:
            for client in (owner, intruder):
                client.rpc("initialize", _init_params(), timeout=20)
            created = owner.rpc(
                "session/new",
                {"cwd": str(tmp_path), "mcpServers": [], "_meta": {"worker": "alpha"}},
                timeout=60,
            )
            session_id = created["sessionId"]

            try:
                intruder.rpc(
                    "session/prompt",
                    {"sessionId": session_id, "prompt": [{"type": "text", "text": "steal"}]},
                    timeout=20,
                )
            except RuntimeError as exc:
                assert "unknown session" in str(exc), exc
            else:
                raise AssertionError("another connection reached a session it does not own")
        finally:
            owner.close()
            intruder.close()
    finally:
        runner.invoke(app, ["pool", "down"])


def test_child_request_reaches_the_host_and_the_answer_gets_home(
    tmp_path: Path, monkeypatch
) -> None:
    isolate(tmp_path, monkeypatch)
    register("asker")
    agent = Path(__file__).parent / "agents" / "perm_agent.py"
    registry_file = registry_path()
    registry = json.loads(registry_file.read_text())
    registry["workers"]["asker"]["stdio_argv"] = [sys.executable, str(agent), "asker"]
    registry_file.write_text(json.dumps(registry))

    bind = os.environ["ACPW_POOL_BIND"]
    up = runner.invoke(app, ["pool", "up", "--bind", bind])
    assert up.exit_code == 0, up.output

    try:
        ran = runner.invoke(app, ["run", "asker", "-p", "please", "--cwd", str(tmp_path)])
        assert ran.exit_code == 0, ran.output
        text = json.loads(ran.output)["text"]
        # The child got a real answer back under its own id 4242, not a timeout or an error.
        assert '"optionId": "allow-once"' in text, text
        assert '"outcome": "selected"' in text, text
    finally:
        runner.invoke(app, ["pool", "down"])


def test_run_prefers_pool_and_no_pool_opts_out(tmp_path: Path, monkeypatch) -> None:
    isolate(tmp_path, monkeypatch)
    register("alpha")

    bind = os.environ["ACPW_POOL_BIND"]
    up = runner.invoke(app, ["pool", "up", "--bind", bind])
    assert up.exit_code == 0, up.output

    try:
        # No per-worker gateway is running, so a success here proves the pool served it.
        ran = runner.invoke(app, ["run", "alpha", "-p", "via-pool", "--cwd", str(tmp_path)])
        assert ran.exit_code == 0, ran.output
        assert json.loads(ran.output)["text"] == "pong:via-pool"

        opted_out = runner.invoke(
            app, ["run", "alpha", "-p", "direct", "--cwd", str(tmp_path), "--no-pool"]
        )
        assert opted_out.exit_code == 1, opted_out.output
        assert json.loads(opted_out.output)["ok"] is False
    finally:
        runner.invoke(app, ["pool", "down"])
