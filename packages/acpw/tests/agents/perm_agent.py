"""Stdio agent that asks the host for permission mid-prompt.

The in-package mock never sends a request upstream, so this is what exercises the
child -> host direction: the daemon must mint an `acpw:<n>` id for the host and write
the answer back under the id the child chose.
"""

from __future__ import annotations

import json
import sys

TAG = sys.argv[1] if len(sys.argv) > 1 else "perm"
# The child-side id the daemon has to restore on the way back.
REQUEST_ID = 4242


def out(obj: dict) -> None:
    print(json.dumps(obj), flush=True)


def read() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    line = line.strip()
    return json.loads(line) if line else {}


def ask_permission(session_id: str) -> str:
    out(
        {
            "jsonrpc": "2.0",
            "id": REQUEST_ID,
            "method": "session/request_permission",
            "params": {
                "sessionId": session_id,
                "options": [{"optionId": "allow-once", "name": "Allow"}],
            },
        }
    )
    while True:
        obj = read()
        if obj is None:
            return "disconnected"
        if obj.get("id") == REQUEST_ID and "method" not in obj:
            return json.dumps(obj.get("result") or obj.get("error"), sort_keys=True)


def main() -> None:
    while True:
        msg = read()
        if msg is None:
            return
        method = msg.get("method")
        msg_id = msg.get("id")
        params = msg.get("params") or {}
        if method == "initialize":
            out(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": 1,
                        "agentCapabilities": {},
                        "authMethods": [{"id": "token", "name": "token"}],
                        "agentInfo": {"name": TAG, "version": "0"},
                    },
                }
            )
        elif method == "authenticate":
            out({"jsonrpc": "2.0", "id": msg_id, "result": {"authed": TAG}})
        elif method == "session/new":
            out({"jsonrpc": "2.0", "id": msg_id, "result": {"sessionId": f"{TAG}-session"}})
        elif method == "session/prompt":
            session_id = params.get("sessionId")
            got = ask_permission(session_id)
            out(
                {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "sessionId": session_id,
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {"type": "text", "text": f"{TAG}:permission={got}"},
                        },
                    },
                }
            )
            out({"jsonrpc": "2.0", "id": msg_id, "result": {"stopReason": "end_turn"}})
        elif msg_id is not None:
            out(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"unknown {method}"},
                }
            )


if __name__ == "__main__":
    main()
