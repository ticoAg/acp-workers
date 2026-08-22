from __future__ import annotations

import contextlib
import os
import shutil
import socket
import tempfile

from acpw import __version__
from acpw.adapters import ADAPTERS
from acpw.install import COMPLETION_DIR
from acpw.paths import PACKAGE_DIR, registry_path, state_dir
from acpw.pool import pool_down, pool_run, pool_up
from acpw.registry import load_registry
from acpw.service import add, doctor, rm
from acpw.types import (
    CheckItem,
    CheckLevel,
    ExecParams,
    SelfCheckResponse,
    WorkerCreateParams,
)
from acpw.ws import split_bind

ROUNDTRIP_PROMPT = "selfcheck"
LOOPBACK = {"127.0.0.1", "localhost", "::1", "[::1]"}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def check_cli() -> CheckItem:
    if __version__ == "0+unknown":
        return CheckItem(
            name="cli",
            level=CheckLevel.fail,
            detail="package metadata missing; acpw is imported from a source tree, not installed",
        )
    return CheckItem(name="cli", level=CheckLevel.ok, detail=f"acpw {__version__} at {PACKAGE_DIR}")


def check_path() -> CheckItem:
    found = shutil.which("acpw")
    if found:
        return CheckItem(name="path", level=CheckLevel.ok, detail=found)
    return CheckItem(
        name="path",
        level=CheckLevel.warn,
        detail="acpw not on PATH; add ~/.local/bin and reopen the shell",
    )


def check_uv() -> CheckItem:
    found = shutil.which("uv")
    if found:
        return CheckItem(name="uv", level=CheckLevel.ok, detail=found)
    return CheckItem(
        name="uv",
        level=CheckLevel.warn,
        detail="uv not on PATH; updates will fail until it is installed",
    )


def check_registry() -> CheckItem:
    path = registry_path()
    try:
        workers = load_registry().workers
    except Exception as exc:  # noqa: BLE001 - any parse failure is the finding
        return CheckItem(name="registry", level=CheckLevel.fail, detail=f"{path}: {exc}")
    return CheckItem(name="registry", level=CheckLevel.ok, detail=f"{path}: {len(workers)} workers")


def check_state() -> CheckItem:
    path = state_dir()
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path):
            pass
    except OSError as exc:
        return CheckItem(name="state", level=CheckLevel.fail, detail=f"{path}: {exc}")
    return CheckItem(name="state", level=CheckLevel.ok, detail=f"{path} is writable")


def check_completion() -> CheckItem:
    path = COMPLETION_DIR / "acpw"
    if path.exists():
        return CheckItem(name="completion", level=CheckLevel.ok, detail=str(path))
    return CheckItem(
        name="completion",
        level=CheckLevel.warn,
        detail="bash completion not registered; run: acpw install",
    )


def check_adapters() -> CheckItem:
    report = doctor()
    present = [row.kind for row in report.adapters if row.present]
    missing = [row.kind for row in report.adapters if not row.present]
    if not present:
        return CheckItem(
            name="adapters",
            level=CheckLevel.fail,
            detail="no agent binary found; install grok, npx, or cursor-agent",
        )
    detail = f"present: {', '.join(present)}"
    if missing:
        return CheckItem(
            name="adapters",
            level=CheckLevel.warn,
            detail=f"{detail}; missing: {', '.join(missing)}",
        )
    return CheckItem(name="adapters", level=CheckLevel.ok, detail=detail)


def check_exposure() -> CheckItem:
    """Workers run with always-approve and the key rides in cleartext, so a LAN bind matters."""
    exposed: list[str] = []
    for name, entry in load_registry().workers.items():
        spec = ADAPTERS.get(entry.kind or name)
        bind = entry.bind or (spec.default_bind if spec else None)
        if not bind:
            continue
        host, _ = split_bind(bind)
        if host not in LOOPBACK:
            exposed.append(f"{name}={bind}")
    if not exposed:
        return CheckItem(name="exposure", level=CheckLevel.ok, detail="all workers bind loopback")
    return CheckItem(
        name="exposure",
        level=CheckLevel.warn,
        detail=(
            f"reachable beyond loopback: {', '.join(sorted(exposed))}; "
            "workers run with always-approve and server-key travels in cleartext"
        ),
    )


def check_roundtrip() -> CheckItem:
    """Start the shared WebSocket, dispatch one prompt through a mock child, read it back."""
    name = f"selfcheck-{os.getpid()}"
    started = False
    try:
        add(WorkerCreateParams(name=name, kind="mock", bind=f"127.0.0.1:{free_port()}"))
        pool_up(workers=[name], cwd=os.getcwd(), timeout=30)
        started = True
        result = pool_run(
            ExecParams(name=name, prompt=ROUNDTRIP_PROMPT, cwd=os.getcwd(), timeout=60)
        )
        expected = f"pong:{ROUNDTRIP_PROMPT}"
        if result.text != expected:
            return CheckItem(
                name="roundtrip",
                level=CheckLevel.fail,
                detail=f"expected {expected!r}, got {result.text!r}",
            )
        return CheckItem(
            name="roundtrip",
            level=CheckLevel.ok,
            detail=f"pool session {result.session_id} answered, stop_reason={result.stop_reason}",
        )
    except Exception as exc:  # noqa: BLE001 - the failure itself is the finding
        return CheckItem(name="roundtrip", level=CheckLevel.fail, detail=str(exc))
    finally:
        if started:
            with contextlib.suppress(Exception):
                pool_down()
        with contextlib.suppress(Exception):  # cleanup must not mask the result
            rm(name)


def run_selfcheck(*, live: bool = True) -> SelfCheckResponse:
    checks = [
        check_cli(),
        check_path(),
        check_uv(),
        check_registry(),
        check_state(),
        check_completion(),
        check_adapters(),
        check_exposure(),
    ]
    if live:
        checks.append(check_roundtrip())
    else:
        checks.append(
            CheckItem(name="roundtrip", level=CheckLevel.warn, detail="skipped (--no-live)")
        )
    failed = [item.name for item in checks if item.level is CheckLevel.fail]
    warned = [item.name for item in checks if item.level is CheckLevel.warn]
    return SelfCheckResponse(
        ok=not failed, version=__version__, checks=checks, warned=warned, failed=failed
    )
