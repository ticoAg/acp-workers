"""Minimal ACP stdio agent for tests."""

from __future__ import annotations

import json
import sys
import uuid

SESSION = "mock-session"


def reply(msg_id, result) -> None:
    print(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": result}), flush=True)


def notify(method: str, params: dict) -> None:
    print(json.dumps({"jsonrpc": "2.0", "method": method, "params": params}), flush=True)


def main() -> None:
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        msg = json.loads(line)
        method = msg.get("method")
        msg_id = msg.get("id")
        params = msg.get("params") or {}
        if method == "initialize":
            reply(
                msg_id,
                {
                    "protocolVersion": 1,
                    "agentCapabilities": {
                        "loadSession": False,
                        "promptCapabilities": {
                            "image": False,
                            "audio": False,
                            "embeddedContext": True,
                        },
                    },
                    "authMethods": [],
                    "agentInfo": {"name": "acpw-mock", "version": "0"},
                },
            )
        elif method == "authenticate":
            reply(msg_id, {})
        elif method == "session/new":
            # One id per session, like a real agent. A fixed id collides in the daemon's
            # (child, native) map, so concurrent session/new would fold into a single
            # session and fan-out would fail with `held by another client`.
            reply(msg_id, {"sessionId": f"mock-{uuid.uuid4().hex[:12]}"})
        elif method == "session/load":
            reply(msg_id, {"sessionId": params.get("sessionId") or SESSION})
        elif method == "session/prompt":
            text = ""
            for block in params.get("prompt") or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    text += str(block.get("text") or "")
            notify(
                "session/update",
                {
                    "sessionId": params.get("sessionId") or SESSION,
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": f"pong:{text[:80]}"},
                    },
                },
            )
            reply(msg_id, {"stopReason": "end_turn"})
        elif method == "session/cancel":
            reply(msg_id, {})
        elif msg_id is not None:
            print(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32601, "message": f"unknown method {method}"},
                    }
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
