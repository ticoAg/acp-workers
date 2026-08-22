from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent

# The multiplexing daemon: one port, one secret, many children.
DEFAULT_POOL_BIND = "0.0.0.0:48190"
POOL_STATE_NAME = "_pool"

# Binds that were once the shipped default. A registry entry still carrying one of these was
# never chosen by the user, so it is migrated to the current default on load.
OLD_DEFAULT_PORTS = {
    "grok": "127.0.0.1:2419",
    "claude": "127.0.0.1:2420",
    "codex": "127.0.0.1:2421",
    "cursor": "127.0.0.1:2422",
    "mock": "127.0.0.1:2499",
}

SUPERSEDED_DEFAULT_BINDS = {
    "grok": "127.0.0.1:48191",
    "claude": "127.0.0.1:48192",
    "codex": "127.0.0.1:48193",
    "cursor": "127.0.0.1:48194",
    "mock": "127.0.0.1:48199",
}


# Resolved per call, not at import: tests and sandboxes set these after the module is loaded.
def config_dir() -> Path:
    return Path(os.environ.get("ACPW_CONFIG_DIR", Path.home() / ".config" / "acp-workers"))


def state_dir() -> Path:
    return Path(os.environ.get("ACPW_STATE_DIR", Path.home() / ".local" / "state" / "acp-workers"))


def registry_path() -> Path:
    return config_dir() / "registry.json"


def config_file() -> Path:
    return config_dir() / "config.json"


def worker_state_dir(name: str) -> Path:
    path = state_dir() / name
    path.mkdir(parents=True, exist_ok=True)
    return path
