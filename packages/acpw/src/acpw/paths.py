from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent

OLD_DEFAULT_PORTS = {
    "grok": "127.0.0.1:2419",
    "claude": "127.0.0.1:2420",
    "codex": "127.0.0.1:2421",
    "cursor": "127.0.0.1:2422",
    "mock": "127.0.0.1:2499",
}


# Resolved per call, not at import: tests and sandboxes set these after the module is loaded.
def config_dir() -> Path:
    return Path(os.environ.get("ACPW_CONFIG_DIR", Path.home() / ".config" / "acp-workers"))


def state_dir() -> Path:
    return Path(os.environ.get("ACPW_STATE_DIR", Path.home() / ".local" / "state" / "acp-workers"))


def registry_path() -> Path:
    return config_dir() / "registry.json"


def worker_state_dir(name: str) -> Path:
    path = state_dir() / name
    path.mkdir(parents=True, exist_ok=True)
    return path
