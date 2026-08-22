from __future__ import annotations

import json
import socket
import sys
import threading
import urllib.parse
from pathlib import Path
from typing import Any

from acpw.paths import worker_state_dir
from acpw.ws import split_bind, ws_accept, ws_recv, ws_send


class StdioChild:
    def __init__(self, argv: list[str], cwd: str):
        import subprocess

        self.proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            bufsize=0,
        )
        assert self.proc.stdin and self.proc.stdout
        self.lock = threading.Lock()
        self.init_result: dict[str, Any] | None = None
        self.auth_result: dict[str, Any] | None = None
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _drain_stderr(self) -> None:
        assert self.proc.stderr
        for line in self.proc.stderr:
            sys.stderr.buffer.write(line)
            sys.stderr.buffer.flush()

    def write_line(self, obj: dict[str, Any]) -> None:
        assert self.proc.stdin
        self.proc.stdin.write((json.dumps(obj, ensure_ascii=False) + "\n").encode())
        self.proc.stdin.flush()

    def read_line(self, timeout: float) -> dict[str, Any] | None:
        assert self.proc.stdout
        line: list[Any] = [None]

        def _read() -> None:
            raw = self.proc.stdout.readline()
            if raw:
                line[0] = json.loads(raw.decode("utf-8", "replace"))

        t = threading.Thread(target=_read, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            return None
        return line[0]

    def alive(self) -> bool:
        return self.proc.poll() is None


def _read_http(conn: socket.socket) -> bytes:
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = conn.recv(4096)
        if not chunk:
            break
        buf += chunk
        if len(buf) > 65536:
            break
    head, _, _rest = buf.partition(b"\r\n\r\n")
    return head


def _bridge_session(conn: socket.socket, child: StdioChild) -> None:
    conn.settimeout(300)
    while True:
        raw = ws_recv(conn)
        if raw is None:
            return
        if not raw:
            continue
        msg = json.loads(raw)
        method = msg.get("method")
        if method == "initialize" and child.init_result is not None:
            ws_send(conn, json.dumps({"jsonrpc": "2.0", "id": msg.get("id"), "result": child.init_result}), client=False)
            continue
        if method == "authenticate" and child.auth_result is not None:
            ws_send(conn, json.dumps({"jsonrpc": "2.0", "id": msg.get("id"), "result": child.auth_result}), client=False)
            continue
        with child.lock:
            child.write_line(msg)
            while True:
                obj = child.read_line(180)
                if obj is None:
                    ws_send(
                        conn,
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "id": msg.get("id"),
                                "error": {"code": -32000, "message": "stdio timeout"},
                            }
                        ),
                        client=False,
                    )
                    return
                if obj.get("id") == msg.get("id"):
                    if method == "initialize" and "result" in obj:
                        child.init_result = obj["result"]
                    if method == "authenticate" and "result" in obj:
                        child.auth_result = obj["result"]
                    ws_send(conn, json.dumps(obj), client=False)
                    break
                ws_send(conn, json.dumps(obj), client=False)


def run_gateway(name: str, bind: str, secret_file: str, stdio: list[str], cwd: str) -> None:
    secret = Path(secret_file).read_text().strip()
    host, port = split_bind(bind)
    child = StdioChild(stdio, cwd)
    (worker_state_dir(name) / "child.pid").write_text(str(child.proc.pid) + "\n")
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(8)
    conn_lock = threading.Lock()

    def handle(conn: socket.socket) -> None:
        try:
            head = _read_http(conn)
            first = head.split(b"\r\n", 1)[0].decode("utf-8", "replace")
            headers: dict[str, str] = {}
            for line in head.split(b"\r\n")[1:]:
                if b":" in line:
                    key, value = line.split(b":", 1)
                    headers[key.decode().lower()] = value.decode().strip()
            if first.startswith("GET /health"):
                body = json.dumps(
                    {
                        "ok": True,
                        "name": name,
                        "transport": "stdio-bridge",
                        "child_alive": child.alive(),
                        "child_pid": child.proc.pid,
                    }
                ).encode()
                conn.sendall(
                    b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: "
                    + str(len(body)).encode()
                    + b"\r\n\r\n"
                    + body
                )
                return
            if not first.startswith("GET /ws"):
                conn.sendall(b"HTTP/1.1 404 Not Found\r\ncontent-length: 0\r\n\r\n")
                return
            path = first.split(" ")[1]
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
            key = (qs.get("server-key") or qs.get("secret") or [None])[0]
            if key != secret:
                msg = b"Invalid or missing authorization token"
                conn.sendall(
                    b"HTTP/1.1 401 Unauthorized\r\ncontent-type: text/plain\r\ncontent-length: "
                    + str(len(msg)).encode()
                    + b"\r\n\r\n"
                    + msg
                )
                return
            ws_key = headers.get("sec-websocket-key")
            if not ws_key:
                conn.sendall(b"HTTP/1.1 400 Bad Request\r\ncontent-length: 0\r\n\r\n")
                return
            accept = ws_accept(ws_key)
            conn.sendall(
                (
                    "HTTP/1.1 101 Switching Protocols\r\n"
                    "Upgrade: websocket\r\n"
                    "Connection: Upgrade\r\n"
                    f"Sec-WebSocket-Accept: {accept}\r\n"
                    "\r\n"
                ).encode()
            )
            with conn_lock:
                _bridge_session(conn, child)
        finally:
            try:
                conn.close()
            except OSError:
                pass

    while child.alive():
        try:
            srv.settimeout(1.0)
            conn, _addr = srv.accept()
        except TimeoutError:
            continue
        threading.Thread(target=handle, args=(conn,), daemon=True).start()
