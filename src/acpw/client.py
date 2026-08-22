from __future__ import annotations

import json
import socket
import time
from typing import Any

from acpw.ws import ws_recv, ws_send


class AcpClient:
    def __init__(self, sock: socket.socket):
        self.sock = sock
        self._n = 0
        self.notifications: list[dict[str, Any]] = []

    def rpc(self, method: str, params: dict[str, Any] | None = None, timeout: float = 60.0) -> dict[str, Any]:
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
                            "result": {"outcome": {"outcome": "selected", "optionId": "allow-once"}},
                        }
                    ),
                    client=True,
                )
                continue
            if obj.get("method") in {"fs/read_text_file", "fs/write_text_file"} and obj.get("id") is not None:
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
