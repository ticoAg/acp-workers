from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from pydantic import BaseModel

from acpw import __version__
from acpw.adapters import ADAPTERS, resolve_stdio_argv
from acpw.daemon import run_daemon
from acpw.gateway import run_gateway
from acpw.install import install_shell, uninstall_shell
from acpw.paths import DEFAULT_POOL_BIND, PACKAGE_DIR
from acpw.pool import (
    pool_down,
    pool_live,
    pool_ping,
    pool_run,
    pool_status,
    pool_stop_worker,
    pool_up,
)
from acpw.registry import AcpwError, load_registry
from acpw.selfcheck import run_selfcheck
from acpw.service import add, doctor, ping, rm, run, start, status, stop
from acpw.types import (
    ErrorResponse,
    ExecParams,
    VersionResponse,
    WorkerCreateParams,
)

app = typer.Typer(
    name="acpw",
    help="One WebSocket, many agents. Host plans; workers execute.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    add_completion=True,
)


def emit(model: BaseModel, *, code: int = 0) -> None:
    typer.echo(model.model_dump_json())
    if code:
        raise typer.Exit(code)


def fail(exc: Exception) -> None:
    if isinstance(exc, AcpwError):
        emit(exc.payload, code=1)
    emit(ErrorResponse(error=str(exc)), code=1)


def poolable(name: str) -> bool:
    """The daemon can own any worker that has a stdio command, including grok."""
    entry = load_registry().workers.get(name)
    spec = ADAPTERS.get((entry.kind if entry else None) or name)
    return bool(resolve_stdio_argv(entry.stdio_argv if entry else None, spec))


def use_pool(name: str, *, url: str | None, choice: bool | None) -> bool:
    """Stdio workers go through the pool by default, starting it if nobody has yet.

    A manual --url names one specific socket, so it is never redirected.
    """
    if choice is False:
        return False
    if choice is None and (url or not poolable(name)):
        return False
    if choice is True and not poolable(name):
        # The daemon only knows how to own stdio children. Say that here rather than
        # letting it fail later as an opaque spawn error.
        raise AcpwError(
            ErrorResponse(
                error=f"worker {name} has no stdio adapter and cannot be pooled; drop --pool",
                name=name,
            )
        )
    if not pool_live():
        pool_up()
    return True


def version_payload() -> VersionResponse:
    return VersionResponse(
        version=__version__,
        python=".".join(str(part) for part in sys.version_info[:3]),
        location=str(PACKAGE_DIR),
    )


def version_option(value: bool) -> None:
    if value:
        emit(version_payload())
        raise typer.Exit()


@app.callback()
def main(
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            help="Print the acpw version and exit.",
            callback=version_option,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """One WebSocket, many agents. Host plans; workers execute."""


@app.command("version")
def cmd_version() -> None:
    """Print the installed acpw version."""
    emit(version_payload())


@app.command("ls")
@app.command("status", hidden=True)
@app.command("discover", hidden=True)
def cmd_ls() -> None:
    """List workers and the shared WebSocket."""
    emit(status())


@app.command("doctor")
def cmd_doctor() -> None:
    """Check adapter binaries on PATH."""
    emit(doctor())


@app.command("selfcheck")
def cmd_selfcheck(
    live: Annotated[
        bool,
        typer.Option("--live/--no-live", help="Dispatch to a throwaway mock worker."),
    ] = True,
) -> None:
    """Verify the installation end to end. Exits 1 if any check fails."""
    result = run_selfcheck(live=live)
    emit(result, code=0 if result.ok else 1)


@app.command("add")
def cmd_add(
    name: str,
    url: Annotated[str | None, typer.Option(help="ws://127.0.0.1:PORT/ws?server-key=...")] = None,
    bind: Annotated[str | None, typer.Option()] = None,
    kind: Annotated[str | None, typer.Option(help="grok|claude|codex|cursor")] = None,
) -> None:
    """Register a worker or a manual websocket URL."""
    try:
        emit(add(WorkerCreateParams(name=name, kind=kind, url=url, bind=bind)))
    except Exception as exc:
        fail(exc)


@app.command("rm")
def cmd_rm(name: str) -> None:
    """Unregister a worker."""
    try:
        emit(rm(name))
    except Exception as exc:
        fail(exc)


@app.command("up")
@app.command("start", hidden=True)
def cmd_up(
    names: Annotated[
        list[str] | None,
        typer.Argument(help="Workers to pre-warm on the pool. Omit to start the socket only."),
    ] = None,
    cwd: Annotated[Path | None, typer.Option()] = None,
    timeout: Annotated[float, typer.Option()] = 45,
    pool: Annotated[
        bool,
        typer.Option(
            "--pool/--no-pool",
            help="Default: the shared WebSocket. --no-pool starts a standalone gateway/serve.",
        ),
    ] = True,
) -> None:
    """Start the shared WebSocket, optionally pre-warming workers."""
    try:
        if pool:
            emit(
                pool_up(
                    workers=list(names) if names else None,
                    cwd=str(cwd) if cwd else None,
                    timeout=timeout,
                )
            )
            return
        if not names:
            emit(ErrorResponse(error="--no-pool needs a worker name"), code=1)
        for name in names:
            emit(start(name, cwd=str(cwd) if cwd else None, timeout=timeout))
    except Exception as exc:
        fail(exc)


@app.command("down")
@app.command("stop", hidden=True)
def cmd_down(
    name: Annotated[
        str | None,
        typer.Argument(help="One pooled child. Omit to stop the shared WebSocket."),
    ] = None,
    pool: Annotated[
        bool,
        typer.Option(
            "--pool/--no-pool",
            help="Default: the shared WebSocket. --no-pool stops a standalone gateway/serve.",
        ),
    ] = True,
) -> None:
    """Stop the shared WebSocket, or one child on it."""
    try:
        if not pool:
            if not name:
                emit(ErrorResponse(error="--no-pool needs a worker name"), code=1)
            emit(stop(name))
            return
        if name is None:
            emit(pool_down())
            return
        emit(pool_stop_worker(name))
    except Exception as exc:
        fail(exc)


@app.command("ping")
def cmd_ping(
    name: str,
    pool: Annotated[
        bool | None,
        typer.Option("--pool/--no-pool", help="Default: the shared WebSocket, for stdio workers."),
    ] = None,
) -> None:
    """ACP initialize against a live worker."""
    try:
        via_pool = use_pool(name, url=None, choice=pool)
        emit(pool_ping(name) if via_pool else ping(name))
    except Exception as exc:
        fail(exc)


@app.command("run")
@app.command("exec", hidden=True)
def cmd_run(
    name: str,
    prompt: Annotated[str | None, typer.Option("-p")] = None,
    prompt_file: Annotated[Path | None, typer.Option("-f", "--prompt-file")] = None,
    cwd: Annotated[Path | None, typer.Option()] = None,
    session_id: Annotated[str | None, typer.Option()] = None,
    url: Annotated[str | None, typer.Option()] = None,
    timeout: Annotated[float, typer.Option()] = 600,
    pool: Annotated[
        bool | None,
        typer.Option("--pool/--no-pool", help="Default: the shared WebSocket, for stdio workers."),
    ] = None,
) -> None:
    """Dispatch a prompt. Returns a session_id; pass --session-id to resume."""
    text = prompt
    if prompt_file:
        text = prompt_file.read_text(encoding="utf-8")
    if not (text or "").strip():
        emit(ErrorResponse(error="empty prompt"), code=1)
    params = ExecParams(
        name=name,
        prompt=text or "",
        cwd=str((cwd or Path.cwd()).resolve()),
        session_id=session_id,
        url=url,
        timeout=timeout,
    )
    try:
        via_pool = use_pool(name, url=url, choice=pool)
        emit(pool_run(params) if via_pool else run(params))
    except Exception as exc:
        fail(exc)


@app.command("install")
def cmd_install() -> None:
    """Register bash completion for this user."""
    emit(install_shell())


@app.command("uninstall")
def cmd_uninstall(
    purge: Annotated[
        bool, typer.Option(help="also stop workers and delete registry/state")
    ] = False,
) -> None:
    """Remove bash completion. Does not uninstall the uv tool or skill."""
    emit(uninstall_shell(purge=purge))


pool_app = typer.Typer(
    name="pool",
    help="One resident daemon, one port, many children.",
    no_args_is_help=True,
)
app.add_typer(pool_app)


@pool_app.command("up")
def cmd_pool_up(
    bind: Annotated[str | None, typer.Option(help=f"Default: {DEFAULT_POOL_BIND}")] = None,
    worker: Annotated[list[str] | None, typer.Option(help="Pre-warm these workers.")] = None,
    cwd: Annotated[Path | None, typer.Option()] = None,
    timeout: Annotated[float, typer.Option()] = 45,
) -> None:
    """Start the pool daemon if it is not live."""
    try:
        emit(
            pool_up(
                bind=bind,
                workers=list(worker) if worker else None,
                cwd=str(cwd) if cwd else None,
                timeout=timeout,
            )
        )
    except Exception as exc:
        fail(exc)


@pool_app.command("down")
def cmd_pool_down() -> None:
    """Stop the pool daemon and every child it owns."""
    emit(pool_down())


@pool_app.command("ls")
@pool_app.command("status", hidden=True)
def cmd_pool_ls() -> None:
    """Pool liveness, children, and session counts."""
    emit(pool_status())


@app.command("daemon", hidden=True)
def cmd_daemon(
    secret_file: Annotated[Path, typer.Option()],
    bind: Annotated[str, typer.Option()] = DEFAULT_POOL_BIND,
) -> None:
    """Internal multiplexing daemon. Started by `acpw up`."""
    run_daemon(bind, str(secret_file))


@app.command("gateway", hidden=True)
def cmd_gateway(
    name: Annotated[str, typer.Option()],
    bind: Annotated[str, typer.Option()],
    secret_file: Annotated[Path, typer.Option()],
    stdio_json: Annotated[str, typer.Option()],
    cwd: Annotated[str, typer.Option()],
) -> None:
    """Internal stdio-to-websocket bridge. Started by `acpw up --no-pool`."""
    run_gateway(name, bind, str(secret_file), json.loads(stdio_json), cwd)
