from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from pydantic import BaseModel

from acpw import __version__
from acpw.gateway import run_gateway
from acpw.install import install_shell, uninstall_shell
from acpw.paths import PACKAGE_DIR
from acpw.registry import AcpwError
from acpw.service import add, doctor, ping, rm, run, start, status, stop
from acpw.types import ErrorResponse, ExecParams, VersionResponse, WorkerCreateParams

app = typer.Typer(
    name="acpw",
    help="Resident ACP workers. Host plans; workers execute.",
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
    """Resident ACP workers. Host plans; workers execute."""


@app.command("version")
def cmd_version() -> None:
    """Print the installed acpw version."""
    emit(version_payload())


@app.command("ls")
@app.command("status", hidden=True)
@app.command("discover", hidden=True)
def cmd_ls() -> None:
    """List workers and live ACP servers."""
    emit(status())


@app.command("doctor")
def cmd_doctor() -> None:
    """Check adapter binaries on PATH."""
    emit(doctor())


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
    name: str,
    cwd: Annotated[Path | None, typer.Option()] = None,
    timeout: Annotated[float, typer.Option()] = 45,
) -> None:
    """Start a worker if it is not live."""
    try:
        emit(start(name, cwd=str(cwd) if cwd else None, timeout=timeout))
    except Exception as exc:
        fail(exc)


@app.command("down")
@app.command("stop", hidden=True)
def cmd_down(name: str) -> None:
    """Stop a worker started by acpw."""
    emit(stop(name))


@app.command("ping")
def cmd_ping(name: str) -> None:
    """ACP initialize against a live worker."""
    try:
        emit(ping(name))
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
) -> None:
    """Dispatch a prompt to a worker."""
    text = prompt
    if prompt_file:
        text = prompt_file.read_text(encoding="utf-8")
    if not (text or "").strip():
        emit(ErrorResponse(error="empty prompt"), code=1)
    try:
        emit(
            run(
                ExecParams(
                    name=name,
                    prompt=text or "",
                    cwd=str((cwd or Path.cwd()).resolve()),
                    session_id=session_id,
                    url=url,
                    timeout=timeout,
                )
            )
        )
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


@app.command("gateway", hidden=True)
def cmd_gateway(
    name: Annotated[str, typer.Option()],
    bind: Annotated[str, typer.Option()],
    secret_file: Annotated[Path, typer.Option()],
    stdio_json: Annotated[str, typer.Option()],
    cwd: Annotated[str, typer.Option()],
) -> None:
    """Internal stdio-to-websocket bridge. Started by `acpw up`."""
    run_gateway(name, bind, str(secret_file), json.loads(stdio_json), cwd)
