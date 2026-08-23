from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from acpw import __version__
from acpw import allow as allow_policy
from acpw.adapters import ADAPTERS
from acpw.client import AcpClient
from acpw.i18n import t
from acpw.paths import PACKAGE_DIR, registry_path, worker_state_dir
from acpw.probe import probe, process_map, scan_listening
from acpw.registry import (
    AcpwError,
    add_worker,
    bind_of,
    ensure_secret,
    load_registry,
    pid_alive,
    read_pid,
    registry_kinds,
    remove_worker,
    require_dispatchable,
    secret_for,
)
from acpw.types import (
    DoctorAdapter,
    DoctorResponse,
    ErrorResponse,
    ExecParams,
    ExecResponse,
    PingResponse,
    ProbeVia,
    ToolCallOut,
    TransportKind,
    WorkerCreateParams,
    WorkerDeleted,
    WorkerRegistered,
    WorkerStartResponse,
    WorkerStatus,
    WorkerStatusList,
    WorkerStopResponse,
)
from acpw.ws import ws_close, ws_connect, ws_url

LIVE = {ProbeVia.health, ProbeVia.ws_401, ProbeVia.ws_auth}


def status() -> WorkerStatusList:
    from acpw.pool import pool_status

    spec_map = ADAPTERS
    pool = pool_status()
    pooled = {row.name: row for row in pool.workers} if pool.live else {}
    extra = registry_kinds()
    policy = allow_policy.current(extra=extra)
    rows: list[WorkerStatus] = []
    for name, entry in load_registry().workers.items():
        kind = entry.kind or name
        spec = spec_map.get(kind)
        transport = spec.transport if spec else TransportKind.remote_ws
        bind = bind_of(entry, spec) if spec else entry.bind
        secret = secret_for(name, entry)
        live = probe(bind, secret) if bind else None
        child = pooled.get(name)
        in_pool = bool(child and child.alive)
        pid = child.pid if in_pool else read_pid(worker_state_dir(name) / "pid")
        rows.append(
            WorkerStatus(
                name=name,
                kind=kind,
                enabled=entry.enabled,
                allowed=allow_policy.kind_allowed(kind, extra=extra),
                transport=transport,
                bind=bind,
                live=in_pool or bool(live and live.live),
                probe="pool" if in_pool else (live.via.value if live and live.via else None),
                pid=pid,
                url=ws_url(bind, None) if bind else entry.url,
                manual_url=bool(entry.url),
                via="pool" if in_pool else ("gateway" if live and live.live else None),
            )
        )
    return WorkerStatusList(
        registry=str(registry_path()),
        workers=rows,
        listening_defaults=scan_listening(),
        processes=process_map(),
        pool=pool,
        allow=policy.allow,
        allow_source=policy.source,
    )


def doctor() -> DoctorResponse:
    items = []
    for kind, spec in ADAPTERS.items():
        if spec.hidden:
            continue
        path = shutil.which(spec.binary) if spec.binary else None
        items.append(
            DoctorAdapter(
                kind=kind,
                transport=spec.transport,
                binary=spec.binary,
                path=path,
                present=bool(path),
                default_bind=spec.default_bind,
            )
        )
    return DoctorResponse(adapters=items, python=sys.executable)


def add(params: WorkerCreateParams) -> WorkerRegistered:
    entry = add_worker(params)
    return WorkerRegistered(
        saved=params.name,
        kind=entry.kind,
        bind=entry.bind,
        url_set=bool(entry.url),
    )


def rm(name: str) -> WorkerDeleted:
    remove_worker(name)
    return WorkerDeleted(removed=name)


def spawn_daemon(argv: list[str], log_path: Path, env: dict[str, str] | None = None) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path, "ab")
    merged = os.environ.copy()
    src = str(PACKAGE_DIR.parent)
    merged["PYTHONPATH"] = src + os.pathsep + merged.get("PYTHONPATH", "")
    if env:
        merged.update(env)
        if "PYTHONPATH" not in env:
            merged["PYTHONPATH"] = src + os.pathsep + merged.get("PYTHONPATH", "")
    for key in ("GROK_AGENT", "GROK_SESSION_ID"):
        merged.pop(key, None)
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        start_new_session=True,
        env=merged,
        cwd=str(Path.cwd()),
    )
    return proc.pid


def wait_live(bind: str, secret: str | None, timeout: float):
    deadline = time.time() + timeout
    last = probe(bind, secret)
    while time.time() < deadline:
        last = probe(bind, secret)
        if last.live and last.via in LIVE:
            return last
        time.sleep(0.25)
    return last


def expand_stdio(argv: list[str]) -> list[str]:
    out = []
    for item in argv:
        if item == "python3":
            out.append(sys.executable)
        else:
            out.append(item)
    return out


def start(name: str, cwd: str | None = None, timeout: float = 45) -> WorkerStartResponse:
    entry, spec = require_dispatchable(name)
    if entry.url:
        live = probe(entry.bind or "127.0.0.1:0", secret_for(name, entry))
        if not live.live:
            raise AcpwError(ErrorResponse(error=t("manual url is not live"), name=name))
        return WorkerStartResponse(name=name, bind=entry.bind, mode="manual-url", live=live)
    bind = entry.bind or spec.default_bind
    secret = ensure_secret(name)
    current = probe(bind, secret)
    if current.live and current.via in LIVE:
        return WorkerStartResponse(name=name, bind=bind, already=True, live=current)
    log_path = worker_state_dir(name) / "server.log"
    workdir = cwd or os.getcwd()
    if spec.transport == TransportKind.native_ws and spec.kind == "grok":
        if not shutil.which("grok"):
            raise AcpwError(ErrorResponse(error=t("grok not on PATH"), name=name))
        argv = [
            "grok",
            "agent",
            "--always-approve",
            "--no-leader",
            "serve",
            "--bind",
            bind,
            "--secret",
            secret,
        ]
        pid = spawn_daemon(argv, log_path, {"GROK_AGENT_SECRET": secret})
    elif spec.transport == TransportKind.stdio_bridge:
        stdio = expand_stdio(list(entry.stdio_argv or spec.stdio_argv))
        if not stdio:
            raise AcpwError(
                ErrorResponse(error=t("{name} missing stdio_argv", name=name), name=name)
            )
        head = stdio[0]
        if head != sys.executable and not shutil.which(head) and not Path(head).exists():
            raise AcpwError(
                ErrorResponse(error=t("binary not on PATH: {head}", head=head), name=name)
            )
        argv = [
            sys.executable,
            "-m",
            "acpw",
            "gateway",
            "--name",
            name,
            "--bind",
            bind,
            "--secret-file",
            str(worker_state_dir(name) / "secret"),
            "--stdio-json",
            __import__("json").dumps(stdio),
            "--cwd",
            workdir,
        ]
        pid = spawn_daemon(argv, log_path)
    else:
        raise AcpwError(
            ErrorResponse(
                error=t(
                    "cannot start transport {transport}; use add --url",
                    transport=spec.transport,
                ),
                name=name,
            )
        )
    (worker_state_dir(name) / "pid").write_text(str(pid) + "\n")
    live = wait_live(bind, secret, timeout)
    ok = bool(live.live and live.via in LIVE)
    if not ok:
        raise AcpwError(
            ErrorResponse(error=t("worker did not become reachable; inspect log"), name=name)
        )
    return WorkerStartResponse(
        name=name,
        bind=bind,
        pid=read_pid(worker_state_dir(name) / "pid"),
        live=live,
        log=str(log_path),
    )


def stop(name: str) -> WorkerStopResponse:
    pid = read_pid(worker_state_dir(name) / "pid")
    child = read_pid(worker_state_dir(name) / "child.pid")
    killed: list[int] = []
    for target in [child, pid]:
        if not target:
            continue
        try:
            os.kill(target, signal.SIGTERM)
            killed.append(target)
        except OSError:
            continue
    time.sleep(0.4)
    for target in killed:
        if pid_alive(target):
            try:
                os.kill(target, signal.SIGKILL)
            except OSError:
                pass
    return WorkerStopResponse(name=name, signaled=killed)


def _load_session_advertised(init: dict) -> bool:
    caps = init.get("agentCapabilities")
    return isinstance(caps, dict) and caps.get("loadSession") is True


def _auth_if_needed(client: AcpClient, init: dict) -> None:
    methods = init.get("authMethods") or []
    default = (init.get("_meta") or {}).get("defaultAuthMethodId")
    method_id = default or (methods[0]["id"] if methods else None)
    if not method_id:
        return
    try:
        client.rpc("authenticate", {"methodId": method_id}, timeout=30)
    except RuntimeError:
        pass


def _collect_text(notes: list[dict]) -> tuple[str, list[ToolCallOut]]:
    chunks: list[str] = []
    tools: list[ToolCallOut] = []
    for note in notes:
        if note.get("method") != "session/update":
            continue
        update = (note.get("params") or {}).get("update") or {}
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


def ping(name: str) -> PingResponse:
    entry, spec = require_dispatchable(name)
    bind = bind_of(entry, spec)
    secret = secret_for(name, entry)
    if not bind:
        raise AcpwError(ErrorResponse(error=t("no bind/url"), name=name))
    live = probe(bind, secret)
    if not live.live:
        raise AcpwError(ErrorResponse(error=t("worker not live"), name=name))
    sock = ws_connect(entry.url or ws_url(bind, secret), timeout=8)
    try:
        client = AcpClient(sock)
        init = client.rpc(
            "initialize",
            {
                "protocolVersion": 1,
                "clientInfo": {"name": "acpw", "version": __version__},
                "clientCapabilities": {
                    "fs": {"readTextFile": False, "writeTextFile": False},
                    "terminal": False,
                },
            },
            timeout=20,
        )
        return PingResponse(
            ok=True,
            name=name,
            protocol_version=init.get("protocolVersion"),
            agent_version=(init.get("_meta") or {}).get("agentVersion"),
            agent_info=init.get("agentInfo") or init.get("serverInfo"),
        )
    finally:
        ws_close(sock, client=True)


def run(params: ExecParams) -> ExecResponse:
    entry, spec = require_dispatchable(params.name)
    bind = bind_of(entry, spec)
    secret = secret_for(params.name, entry)
    url = params.url or entry.url or (ws_url(bind, secret) if bind else None)
    if not url:
        raise AcpwError(ErrorResponse(error=t("no websocket url"), name=params.name))
    sock = ws_connect(url, timeout=8)
    try:
        client = AcpClient(sock)
        init = client.rpc(
            "initialize",
            {
                "protocolVersion": 1,
                "clientInfo": {"name": "acpw", "version": __version__},
                "clientCapabilities": {
                    "fs": {"readTextFile": False, "writeTextFile": False},
                    "terminal": False,
                },
            },
            timeout=30,
        )
        _auth_if_needed(client, init)
        if params.session_id:
            if not _load_session_advertised(init):
                raise AcpwError(
                    ErrorResponse(
                        error=t(
                            "worker {name} cannot resume sessions (loadSession not advertised)",
                            name=params.name,
                        ),
                        name=params.name,
                    )
                )
            session = client.rpc(
                "session/load",
                {"sessionId": params.session_id, "cwd": params.cwd, "mcpServers": []},
                timeout=30,
            )
            session_id = session.get("sessionId") or params.session_id
        else:
            session = client.rpc(
                "session/new",
                {"cwd": params.cwd, "mcpServers": [], "_meta": {"yoloMode": True}},
                timeout=60,
            )
            session_id = session.get("sessionId")
        result = client.rpc(
            "session/prompt",
            {"sessionId": session_id, "prompt": [{"type": "text", "text": params.prompt}]},
            timeout=params.timeout,
        )
        text, tools = _collect_text(client.notifications)
        return ExecResponse(
            ok=True,
            name=params.name,
            session_id=session_id,
            stop_reason=result.get("stopReason"),
            text=text,
            tool_calls=tools,
        )
    finally:
        ws_close(sock, client=True)
