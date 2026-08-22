from __future__ import annotations

import json
import socket
import threading
import time
from typing import Any

from acpw.ws import ws_recv, ws_send


class AcpClient:
    def __init__(self, sock: socket.socket):
        self.sock = sock
        self._n = 0
        self.notifications: list[dict[str, Any]] = []

    def rpc(
        self, method: str, params: dict[str, Any] | None = None, timeout: float = 60.0
    ) -> dict[str, Any]:
        self._n += 1
        msg_id = self._n
        self.sock.settimeout(timeout)
        ws_send(
            self.sock,
            json.dumps({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}}),
            client=True,
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            left = max(0.1, deadline - time.time())
            self.sock.settimeout(left)
            raw = ws_recv(self.sock)
            if raw is None:
                raise ConnectionError("ACP connection closed")
            if not raw:
                continue
            obj = json.loads(raw)
            if obj.get("id") == msg_id:
                if "error" in obj:
                    raise RuntimeError(json.dumps(obj["error"], ensure_ascii=False))
                return obj.get("result") or {}
            if obj.get("method") == "session/request_permission" and obj.get("id") is not None:
                ws_send(
                    self.sock,
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": obj["id"],
                            "result": {
                                "outcome": {"outcome": "selected", "optionId": "allow-once"}
                            },
                        }
                    ),
                    client=True,
                )
                continue
            if (
                obj.get("method") in {"fs/read_text_file", "fs/write_text_file"}
                and obj.get("id") is not None
            ):
                ws_send(
                    self.sock,
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": obj["id"],
                            "error": {"code": -32601, "message": "client fs not offered"},
                        }
                    ),
                    client=True,
                )
                continue
            if "method" in obj:
                self.notifications.append(obj)
        raise TimeoutError(f"timeout waiting for {method}")


class _Reply:
    __slots__ = ("error", "event", "payload")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.payload: dict[str, Any] | None = None
        self.error: BaseException | None = None


class MuxClient:
    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self._n = 0
        self._n_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._lock = threading.Lock()
        self._pending: dict[Any, _Reply] = {}
        self._updates: dict[str, list[dict[str, Any]]] = {}
        self._thread: threading.Thread | None = None
        self._closed = False

    def start(self) -> None:
        if self._thread is not None:
            return
        self.sock.settimeout(None)
        self._thread = threading.Thread(target=self._read_loop, name="acpw-mux-reader", daemon=True)
        self._thread.start()

    def close(self) -> None:
        with self._lock:
            self._closed = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._fail_pending(ConnectionError("ACP connection closed"))

    def rpc(
        self, method: str, params: dict[str, Any] | None = None, timeout: float = 60.0
    ) -> dict[str, Any]:
        with self._n_lock:
            self._n += 1
            msg_id = self._n
        reply = _Reply()
        with self._lock:
            if self._closed:
                raise ConnectionError("ACP connection closed")
            self._pending[msg_id] = reply
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}}
        )
        try:
            with self._write_lock:
                ws_send(self.sock, payload, client=True)
        except OSError as exc:
            with self._lock:
                self._pending.pop(msg_id, None)
            raise ConnectionError("ACP connection closed") from exc
        if not reply.event.wait(timeout):
            with self._lock:
                self._pending.pop(msg_id, None)
            raise TimeoutError(f"timeout waiting for {method}")
        if reply.error is not None:
            raise reply.error
        return reply.payload or {}

    def updates(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._updates.get(session_id, []))

    def _fail_pending(self, exc: BaseException) -> None:
        with self._lock:
            pending = self._pending
            self._pending = {}
            self._closed = True
        for reply in pending.values():
            if not reply.event.is_set():
                reply.error = exc
                reply.event.set()

    def _send(self, obj: dict[str, Any]) -> None:
        with self._write_lock:
            ws_send(self.sock, json.dumps(obj), client=True)

    def _complete(self, msg_id: object, obj: dict[str, Any]) -> None:
        with self._lock:
            reply = self._pending.pop(msg_id, None)
        if reply is None:
            return
        if "error" in obj:
            reply.error = RuntimeError(json.dumps(obj["error"], ensure_ascii=False))
        else:
            reply.payload = obj.get("result") or {}
        reply.event.set()

    def _handle_request(self, method: str, msg_id: object) -> None:
        if method == "session/request_permission":
            self._send(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {"outcome": {"outcome": "selected", "optionId": "allow-once"}},
                }
            )
            return
        if method.startswith(("fs/", "terminal/")):
            self._send(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": "client fs not offered"},
                }
            )

    def _dispatch(self, obj: dict[str, Any]) -> None:
        method = obj.get("method")
        msg_id = obj.get("id")
        if method is None and msg_id is not None:
            self._complete(msg_id, obj)
            return
        if method and msg_id is not None:
            self._handle_request(method, msg_id)
            return
        if method == "session/update":
            params = obj.get("params") or {}
            session_id = params.get("sessionId")
            if session_id is not None:
                with self._lock:
                    self._updates.setdefault(str(session_id), []).append(params)

    def _read_loop(self) -> None:
        try:
            while True:
                try:
                    raw = ws_recv(self.sock)
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
                if not isinstance(obj, dict):
                    continue
                try:
                    self._dispatch(obj)
                except OSError:
                    break
        finally:
            self._fail_pending(ConnectionError("ACP connection closed"))
