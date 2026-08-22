from __future__ import annotations

import secrets
import urllib.parse
from pathlib import Path

from acpw.adapters import ADAPTERS
from acpw.io import load_json, save_json
from acpw.paths import (
    OLD_DEFAULT_PORTS,
    SUPERSEDED_DEFAULT_BINDS,
    registry_path,
    worker_state_dir,
)
from acpw.types import Adapter, ErrorResponse, Registry, TransportKind, Worker, WorkerCreateParams
from acpw.ws import split_bind


class AcpwError(Exception):
    def __init__(self, payload: ErrorResponse):
        super().__init__(payload.error)
        self.payload = payload


def default_registry() -> Registry:
    workers = {
        kind: Worker(kind=kind, enabled=True, bind=spec.default_bind)
        for kind, spec in ADAPTERS.items()
        if not spec.hidden
    }
    return Registry(workers=workers)


def load_registry() -> Registry:
    raw = load_json(registry_path(), None)
    if raw is None:
        data = default_registry()
        save_json(registry_path(), data)
        return data
    data = Registry.model_validate(raw)
    changed = False
    for name, worker in data.workers.items():
        kind = worker.kind or name
        spec = ADAPTERS.get(kind)
        if not spec or worker.url:
            continue
        stale = {OLD_DEFAULT_PORTS.get(kind), SUPERSEDED_DEFAULT_BINDS.get(kind)}
        if worker.bind in stale - {None}:
            worker.bind = spec.default_bind
            changed = True
    if changed:
        save_json(registry_path(), data)
    return data


def save_registry(data: Registry) -> None:
    save_json(registry_path(), data)


def resolve_worker(name: str) -> tuple[Worker, Adapter]:
    data = load_registry()
    if name not in data.workers:
        raise AcpwError(ErrorResponse(error=f"unknown worker {name}", known=sorted(data.workers)))
    entry = data.workers[name]
    kind = entry.kind or name
    spec = ADAPTERS.get(kind)
    if spec is None and not entry.url:
        raise AcpwError(ErrorResponse(error=f"unknown kind {kind}", name=name))
    if spec is None:
        spec = Adapter(
            kind=kind,
            transport=TransportKind.remote_ws,
            default_bind=entry.bind or "127.0.0.1:0",
        )
    bind = entry.bind or spec.default_bind
    if not entry.bind:
        entry.bind = bind
    return entry, spec


def secret_for(name: str, entry: Worker) -> str | None:
    if entry.url:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(entry.url).query)
        keys = qs.get("server-key") or qs.get("secret") or []
        return keys[0] if keys else None
    path = worker_state_dir(name) / "secret"
    if path.exists():
        value = path.read_text().strip()
        return value or None
    return None


def ensure_secret(name: str) -> str:
    path = worker_state_dir(name) / "secret"
    if path.exists():
        value = path.read_text().strip()
        if value:
            return value
    value = secrets.token_hex(16)
    path.write_text(value + "\n")
    path.chmod(0o600)
    return value


def add_worker(params: WorkerCreateParams) -> Worker:
    data = load_registry()
    entry = Worker(kind=params.kind or params.name, enabled=True)
    if params.url:
        entry.url = params.url
        parsed = urllib.parse.urlparse(params.url)
        if parsed.hostname and parsed.port:
            entry.bind = f"{parsed.hostname}:{parsed.port}"
    if params.bind:
        entry.bind = params.bind
    data.workers[params.name] = entry
    save_registry(data)
    return entry


def remove_worker(name: str) -> None:
    data = load_registry()
    if name not in data.workers:
        raise AcpwError(ErrorResponse(error=f"unknown worker {name}", known=sorted(data.workers)))
    del data.workers[name]
    save_registry(data)


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import os

        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_pid(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        pid = int(path.read_text().strip())
    except ValueError:
        return None
    return pid if pid_alive(pid) else None


def bind_of(entry: Worker, spec: Adapter) -> str | None:
    if entry.url:
        parsed = urllib.parse.urlparse(entry.url)
        if parsed.hostname:
            return f"{parsed.hostname}:{parsed.port or 80}"
    return entry.bind or spec.default_bind


def split_host_port(bind: str) -> tuple[str, int]:
    return split_bind(bind)
