"""Stdio ACP agent that persists sessions, so `session/load` really restores history.

The in-package mock forgets everything when it exits, which is exactly what the pool's
durability tiers need to survive. This one keeps its conversations in a file and echoes
the whole history back, so a resumed session is distinguishable from a fresh one.

On `session/load` a native id is rewritten to `reloaded:<id>` unless it already is one:
agents are allowed to hand back a different id than they were given, and the daemon has
to follow that without changing the public id it promised the host.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

STORE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("resume-store.json")
TAG = sys.argv[2] if len(sys.argv) > 2 else "resumer"


def out(obj: dict) -> None:
    print(json.dumps(obj), flush=True)


def read() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    line = line.strip()
    return json.loads(line) if line else {}


def load_store() -> dict:
    if not STORE.is_file():
        return {"n": 0, "sessions": {}}
    try:
        data = json.loads(STORE.read_text())
    except (OSError, json.JSONDecodeError):
        return {"n": 0, "sessions": {}}
    if not isinstance(data, dict):
        return {"n": 0, "sessions": {}}
    data.setdefault("n", 0)
    data.setdefault("sessions", {})
    return data


def save_store(data: dict) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(STORE)


def migrate(sessions: dict, native: str) -> str:
    if native.startswith("reloaded:"):
        sessions.setdefault(native, {"prompts": []})
        return native
    new = f"reloaded:{native}"
    old = sessions.pop(native, None) or {"prompts": []}
    existing = sessions.get(new)
    if existing is None:
        sessions[new] = old
    else:
        existing.setdefault("prompts", []).extend(old.get("prompts") or [])
    return new


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
                        "agentCapabilities": {
                            "loadSession": True,
                            "promptCapabilities": {
                                "image": False,
                                "audio": False,
                                "embeddedContext": True,
                            },
                        },
                        "authMethods": [],
                        "agentInfo": {"name": TAG, "version": "0"},
                    },
                }
            )
        elif method == "authenticate":
            out({"jsonrpc": "2.0", "id": msg_id, "result": {}})
        elif method == "session/new":
            data = load_store()
            data["n"] = int(data.get("n") or 0) + 1
            native = f"nat-{data['n']}"
            data["sessions"][native] = {"prompts": []}
            save_store(data)
            out({"jsonrpc": "2.0", "id": msg_id, "result": {"sessionId": native}})
        elif method == "session/load":
            data = load_store()
            native = str(params.get("sessionId") or "")
            loaded = migrate(data["sessions"], native)
            save_store(data)
            out({"jsonrpc": "2.0", "id": msg_id, "result": {"sessionId": loaded}})
        elif method == "session/prompt":
            data = load_store()
            native = str(params.get("sessionId") or "")
            text = ""
            for block in params.get("prompt") or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    text += str(block.get("text") or "")
            slot = data["sessions"].setdefault(native, {"prompts": []})
            slot["prompts"].append(text)
            save_store(data)
            hist = "|".join(slot["prompts"])
            out(
                {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "sessionId": native,
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {"type": "text", "text": f"hist:{hist}"},
                        },
                    },
                }
            )
            out({"jsonrpc": "2.0", "id": msg_id, "result": {"stopReason": "end_turn"}})
        elif method == "session/cancel":
            out({"jsonrpc": "2.0", "id": msg_id, "result": {}})
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
