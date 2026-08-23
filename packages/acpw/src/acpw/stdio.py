"""Standard ACP stdio face for one pooled worker.

Editors and acp-devtools spawn this as a subprocess. JSON-RPC ids pass through
unchanged; the only mutation is injecting `_meta.worker` so the daemon can route.
"""

from __future__ import annotations

import json
import socket
import sys
import threading
from typing import Any

from acpw.adapters import ADAPTERS, resolve_stdio_argv
from acpw.i18n import t
from acpw.pool import pool_live, pool_up, pool_url
from acpw.registry import AcpwError, load_registry, require_dispatchable
from acpw.ws import ws_close, ws_connect, ws_recv, ws_send

WORKER_METHODS = frozenset({"worker/list", "worker/up", "worker/down"})
SESSION_OPEN = frozenset({"session/new", "session/load"})


def run_stdio(name: str, *, url: str | None = None) -> int:
    try:
        require_dispatchable(name)
    except AcpwError as exc:
        return _die(exc.payload.error)
    if url is None:
        if not _poolable(name):
            return _die(t("worker {name} has no stdio adapter", name=name))
        try:
            if not pool_live():
                pool_up()
            url = pool_url()
        except AcpwError as exc:
            return _die(exc.payload.error)
        except Exception as exc:  # noqa: BLE001 - startup must not write ACP to stdout
            return _die(t("cannot connect: {error}", error=str(exc)))
    try:
        sock = ws_connect(url, timeout=8)
    except Exception as exc:  # noqa: BLE001
        if "401" in str(exc):
            from acpw.paths import POOL_STATE_NAME, worker_state_dir
            from acpw.pool import pool_status

            return _die(
                t(
                    "pool on {bind} rejected our key: it was started with a "
                    "different secret than {secret}. Run 'acpw pool down' "
                    "and start it again, or point ACPW_STATE_DIR at the one it uses.",
                    bind=pool_status().bind,
                    secret=worker_state_dir(POOL_STATE_NAME) / "secret",
                )
            )
        return _die(t("cannot connect: {error}", error=str(exc)))
    return _pump(sock, name)


def _poolable(name: str) -> bool:
    entry = load_registry().workers.get(name)
    spec = ADAPTERS.get((entry.kind if entry else None) or name)
    return bool(resolve_stdio_argv(entry.stdio_argv if entry else None, spec))


def _die(message: str) -> int:
    sys.stderr.write(f"acpw stdio: {message}\n")
    sys.stderr.flush()
    return 1


def _inject_worker(obj: dict[str, Any], worker: str) -> dict[str, Any]:
    params = obj.get("params")
    params = dict(params) if isinstance(params, dict) else {}
    meta = params.get("_meta")
    meta = dict(meta) if isinstance(meta, dict) else {}
    meta["worker"] = worker
    params["_meta"] = meta
    return {**obj, "params": params}


def _rewrite_initialize(obj: dict[str, Any], worker: str) -> dict[str, Any]:
    if obj.get("method") is not None:
        return obj
    result = obj.get("result")
    if not isinstance(result, dict) or "protocolVersion" not in result:
        return obj
    info = result.get("agentInfo")
    info = dict(info) if isinstance(info, dict) else {}
    info["name"] = f"acpw/{worker}"
    return {**obj, "result": {**result, "agentInfo": info}}


def _method_not_found(msg_id: Any) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": "Method not found"},
    }


def _pump(sock: socket.socket, worker: str) -> int:
    ws_lock = threading.Lock()
    out_lock = threading.Lock()
    closed = threading.Event()
    stdin_eof = threading.Event()

    def send_ws(obj: dict[str, Any]) -> None:
        payload = json.dumps(obj, ensure_ascii=False)
        with ws_lock:
            ws_send(sock, payload, client=True)

    def send_out(obj: dict[str, Any]) -> None:
        line = (json.dumps(obj, ensure_ascii=False) + "\n").encode()
        with out_lock:
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()

    def inbound() -> None:
        try:
            while not closed.is_set():
                raw = sys.stdin.buffer.readline()
                if not raw:
                    break
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    sys.stderr.write(f"acpw stdio: bad json: {exc}\n")
                    sys.stderr.flush()
                    continue
                if not isinstance(obj, dict):
                    continue
                method = obj.get("method")
                if method in WORKER_METHODS:
                    if obj.get("id") is not None:
                        send_out(_method_not_found(obj.get("id")))
                    continue
                if method in SESSION_OPEN:
                    obj = _inject_worker(obj, worker)
                try:
                    send_ws(obj)
                except OSError:
                    break
        finally:
            stdin_eof.set()
            closed.set()
            ws_close(sock, client=True)

    def outbound() -> None:
        try:
            while not closed.is_set():
                try:
                    raw = ws_recv(sock, client=True)
                except (OSError, TimeoutError, ValueError):
                    break
                if raw is None:
                    break
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    send_out(_rewrite_initialize(obj, worker))
        finally:
            closed.set()
            ws_close(sock, client=True)

    reader = threading.Thread(target=inbound, name="acpw-stdio-in", daemon=True)
    writer = threading.Thread(target=outbound, name="acpw-stdio-out", daemon=True)
    writer.start()
    reader.start()
    try:
        while reader.is_alive() and writer.is_alive():
            reader.join(timeout=0.2)
        if stdin_eof.is_set():
            writer.join(timeout=2.0)
            return 0
        ws_close(sock, client=True)
        reader.join(timeout=0.2)
        return 1
    except KeyboardInterrupt:
        ws_close(sock, client=True)
        return 130
