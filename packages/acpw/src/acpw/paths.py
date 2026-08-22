from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent

CONFIG_DIR = Path(os.environ.get("ACPW_CONFIG_DIR", Path.home() / ".config" / "acp-workers"))
STATE_DIR = Path(os.environ.get("ACPW_STATE_DIR", Path.home() / ".local" / "state" / "acp-workers"))
REGISTRY_PATH = CONFIG_DIR / "registry.json"

OLD_DEFAULT_PORTS = {
    "grok": "127.0.0.1:2419",
    "claude": "127.0.0.1:2420",
    "codex": "127.0.0.1:2421",
    "cursor": "127.0.0.1:2422",
    "mock": "127.0.0.1:2499",
}


def worker_state_dir(name: str) -> Path:
    path = STATE_DIR / name
    path.mkdir(parents=True, exist_ok=True)
    return path
