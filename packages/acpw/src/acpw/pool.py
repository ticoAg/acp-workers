from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

from acpw import __version__
from acpw.client import MuxClient
from acpw.paths import DEFAULT_POOL_BIND, POOL_STATE_NAME, worker_state_dir
from acpw.probe import http_get
from acpw.registry import AcpwError, ensure_secret, pid_alive, read_pid
from acpw.service import spawn_daemon
from acpw.types import (
    ErrorResponse,
    ExecParams,
    ExecResponse,
    PingResponse,
    PoolStartResponse,
    PoolStatus,
    PoolStopResponse,
    PoolWorker,
    ToolCallOut,
)
from acpw.ws import connect_host, split_bind, ws_connect, ws_url


def _state() -> Path:
    return worker_state_dir(POOL_STATE_NAME)


def _resolved_bind() -> str:
    env = os.environ.get("ACPW_POOL_BIND", "").strip()
    if env:
        return env
    path = _state() / "bind"
    if path.exists():
        value = path.read_text().strip()
        if value:
            return value
    return DEFAULT_POOL_BIND


def _health(bind: str, timeout: float) -> tuple[int, dict[str, Any]]:
    host, port = split_bind(bind)
    host = connect_host(host)
    code, body = http_get(f"http://{host}:{port}/health", timeout=timeout)
    if code != 200:
        return code, {}
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        payload = {}
    return code, payload if isinstance(payload, dict) else {}


def _workers_from_health(payload: dict[str, Any]) -> list[PoolWorker]:
    workers: list[PoolWorker] = []
    for item in payload.get("workers") or []:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        workers.append(
            PoolWorker(
                name=str(item["name"]),
                kind=str(item.get("kind") or item["name"]),
                alive=bool(item.get("alive")),
                pid=item.get("pid"),
                sessions=int(item.get("sessions") or 0),
            )
        )
    return workers


def _init_params() -> dict[str, Any]:
    return {
        "protocolVersion": 1,
        "clientInfo": {"name": "acpw", "version": __version__},
        "clientCapabilities": {
            "fs": {"readTextFile": False, "writeTextFile": False},
            "terminal": False,
        },
    }


def _auth_if_needed(client: MuxClient, init: dict[str, Any]) -> None:
    methods = init.get("authMethods") or []
    default = (init.get("_meta") or {}).get("defaultAuthMethodId")
    method_id = default or (methods[0]["id"] if methods else None)
    if not method_id:
        return
    try:
        client.rpc("authenticate", {"methodId": method_id}, timeout=30)
    except RuntimeError:
        pass


def _collect_text(updates: list[dict[str, Any]]) -> tuple[str, list[ToolCallOut]]:
    chunks: list[str] = []
    tools: list[ToolCallOut] = []
    for params in updates:
        update = params.get("update") or {}
        kind = update.get("sessionUpdate")
        if kind == "agent_message_chunk":
            content = update.get("content") or {}
            if isinstance(content, dict) and content.get("text"):
                chunks.append(str(content["text"]))
        elif kind in {"tool_call", "tool_call_update"}:
            tools.append(
                ToolCallOut(
                    kind=kind,
                    title=update.get("title"),
                    status=update.get("status"),
                    name=update.get("toolCallName") or update.get("name"),
                )
            )
    return "".join(chunks), tools


def _open_mux(url: str) -> MuxClient:
    try:
        sock = ws_connect(url, timeout=8)
    except Exception as exc:
        if "401" in str(exc):
            # /health needs no key, so a daemon started against a different state
            # directory looks perfectly alive right up to the moment we authenticate.
            raise AcpwError(
                ErrorResponse(
                    error=(
                        f"pool on {_resolved_bind()} rejected our key: it was started with a "
                        f"different secret than {_state() / 'secret'}. Run 'acpw pool down' "
                        "and start it again, or point ACPW_STATE_DIR at the one it uses."
                    )
                )
            ) from exc
        raise
    client = MuxClient(sock)
    client.start()
    return client


def _rpc_error_parts(exc: BaseException) -> tuple[int | None, str]:
    raw = str(exc)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None, raw
    if not isinstance(payload, dict):
        return None, raw
    code = payload.get("code")
    message = payload.get("message")
    text = message.strip() if isinstance(message, str) and message.strip() else raw
    return (code if isinstance(code, int) else None), text


def _resume_error(name: str, session_id: str, exc: BaseException) -> AcpwError:
    code, message = _rpc_error_parts(exc)
    lowered = message.lower()
    if "held by another client" in lowered:
        text = f"session {session_id} is held by another client"
    elif "loadsession" in lowered or "cannot resume" in lowered:
        text = (
            message
            if "cannot resume" in lowered
            else f"worker {name} cannot resume sessions (loadSession not advertised)"
        )
    elif "unknown session" in lowered:
        text = f"unknown session {session_id}"
    elif code == -32001:
        text = message
    else:
        text = f"cannot resume session {session_id}: {message}"
    return AcpwError(ErrorResponse(error=text, name=name))


def pool_secret() -> str:
    return ensure_secret(POOL_STATE_NAME)


def pool_url(secret: str | None = None) -> str:
    return ws_url(_resolved_bind(), secret if secret is not None else pool_secret())


def pool_live(timeout: float = 1.0) -> bool:
    code, _payload = _health(_resolved_bind(), timeout)
    return code == 200


def pool_status() -> PoolStatus:
    bind = _resolved_bind()
    log = str(_state() / "server.log")
    url = pool_url()
    try:
        code, payload = _health(bind, 1.0)
    except OSError:
        return PoolStatus(live=False, bind=bind, url=url, log=log, workers=[])
    if code != 200:
        return PoolStatus(live=False, bind=bind, url=url, log=log, workers=[])
    return PoolStatus(
        ok=bool(payload.get("ok", True)),
        live=True,
        bind=bind,
        url=url,
        pid=payload.get("pid"),
        workers=_workers_from_health(payload),
        sessions=int(payload.get("sessions") or 0),
        log=log,
    )


def pool_up(
    bind: str | None = None,
    workers: list[str] | None = None,
    cwd: str | None = None,
    timeout: float = 45,
) -> PoolStartResponse:
    # Everything else asks _resolved_bind() where the pool is, so starting one anywhere
    # else just produces a daemon nobody can find.
    bind = bind or _resolved_bind()
    secret = pool_secret()
    state = _state()
    log_path = state / "server.log"
    if pool_live():
        current = pool_status()
        if workers:
            _prewarm(pool_url(secret), workers, cwd, timeout)
            current = pool_status()
        return PoolStartResponse(
            bind=current.bind,
            url=current.url,
            pid=current.pid,
            already=True,
            log=current.log,
            workers=current.workers,
        )
    secret_file = state / "secret"
    (state / "bind").write_text(bind + "\n")
    argv = [
        sys.executable,
        "-m",
        "acpw",
        "daemon",
        "--bind",
        bind,
        "--secret-file",
        str(secret_file),
    ]
    pid = spawn_daemon(argv, log_path)
    (state / "pid").write_text(str(pid) + "\n")
    deadline = time.time() + timeout
    code = 0
    payload: dict[str, Any] = {}
    while time.time() < deadline:
        left = max(0.1, min(1.0, deadline - time.time()))
        try:
            code, payload = _health(bind, left)
        except OSError:
            code, payload = 0, {}
        if code == 200:
            break
        time.sleep(0.25)
    if code != 200:
        raise AcpwError(ErrorResponse(error="pool did not become reachable; inspect log"))
    url = ws_url(bind, secret)
    if workers:
        _prewarm(url, workers, cwd, max(1.0, deadline - time.time()))
        _, payload = _health(bind, 1.0)
    return PoolStartResponse(
        bind=bind,
        url=url,
        pid=payload.get("pid") or read_pid(state / "pid"),
        already=False,
        log=str(log_path),
        workers=_workers_from_health(payload),
    )


def _prewarm(url: str, workers: list[str], cwd: str | None, timeout: float) -> None:
    client = _open_mux(url)
    try:
        client.rpc("initialize", _init_params(), timeout=min(30.0, max(5.0, timeout)))
        per = max(5.0, timeout)
        for name in workers:
            params: dict[str, Any] = {"name": name}
            if cwd is not None:
                params["cwd"] = cwd
            client.rpc("worker/up", params, timeout=per)
    finally:
        client.close()


def pool_down() -> PoolStopResponse:
    pid = read_pid(_state() / "pid")
    killed: list[int] = []
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except OSError:
            pass
    time.sleep(0.4)
    for target in killed:
        if pid_alive(target):
            try:
                os.kill(target, signal.SIGKILL)
            except OSError:
                pass
    live = False
    try:
        live = pool_live()
    except OSError:
        live = False
    return PoolStopResponse(signaled=killed, live=live)


def pool_ping(name: str) -> PingResponse:
    """Reach the named worker, not just the daemon in front of it.

    Handshaking with the pool proves nothing about the agent the caller asked for, so
    this spawns the child if needed and reports what that child said about itself.
    """
    if not pool_live():
        raise AcpwError(ErrorResponse(error="pool not live", name=name))
    client = _open_mux(pool_url())
    try:
        client.rpc("initialize", _init_params(), timeout=20)
        worker = client.rpc("worker/up", {"name": name}, timeout=60)
        return PingResponse(
            ok=bool(worker.get("alive")),
            name=name,
            protocol_version=worker.get("protocolVersion"),
            agent_version=worker.get("agentVersion"),
            agent_info=worker.get("agentInfo"),
        )
    finally:
        client.close()


def pool_run(params: ExecParams) -> ExecResponse:
    url = params.url or pool_url()
    client = _open_mux(url)
    try:
        init = client.rpc("initialize", _init_params(), timeout=30)
        _auth_if_needed(client, init)
        worker_meta = {"worker": params.name}
        if params.session_id:
            # Resume is the daemon's job. Hand the id to session/prompt; never session/new
            # or session/load — a silent new session would drop the conversation.
            session_id = params.session_id
        else:
            session = client.rpc(
                "session/new",
                {
                    "cwd": params.cwd,
                    "mcpServers": [],
                    "_meta": {**worker_meta, "yoloMode": True},
                },
                timeout=60,
            )
            session_id = session.get("sessionId")
        try:
            result = client.rpc(
                "session/prompt",
                {"sessionId": session_id, "prompt": [{"type": "text", "text": params.prompt}]},
                timeout=params.timeout,
            )
        except RuntimeError as exc:
            if params.session_id:
                raise _resume_error(params.name, params.session_id, exc) from exc
            raise
        text, tools = _collect_text(client.updates(session_id or ""))
        return ExecResponse(
            ok=True,
            name=params.name,
            session_id=session_id,
            stop_reason=result.get("stopReason"),
            text=text,
            tool_calls=tools,
        )
    finally:
        client.close()
