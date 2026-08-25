from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from typer.core import TyperGroup

from acpw import __version__
from acpw import allow as allow_policy
from acpw import output as out
from acpw.adapters import ADAPTERS, resolve_stdio_argv
from acpw.daemon import run_daemon
from acpw.gateway import run_gateway
from acpw.i18n import (
    SUPPORTED,
    LangState,
    apply,
    bootstrap,
    current,
    normalize,
    save_lang,
    strip_lang,
    t,
)
from acpw.install import install_shell, uninstall_shell
from acpw.paths import DEFAULT_POOL_BIND, PACKAGE_DIR
from acpw.pool import (
    pool_down,
    pool_live,
    pool_ping,
    pool_run,
    pool_session_delete,
    pool_sessions,
    pool_sessions_prune,
    pool_status,
    pool_stop_worker,
    pool_up,
)
from acpw.registry import AcpwError, load_registry, require_dispatchable
from acpw.selfcheck import run_selfcheck
from acpw.service import add, doctor, ping, rm, run, start, status, stop
from acpw.stdio import run_stdio
from acpw.types import (
    ErrorResponse,
    ExecParams,
    LangResponse,
    OutputResponse,
    VersionResponse,
    WorkerCreateParams,
)


class LocaleGroup(TyperGroup):
    def main(self, args: Any = None, **kwargs: Any) -> Any:
        argv = list(args) if args is not None else sys.argv[1:]
        fmt, stripped = out.strip_output(argv)
        flag, stripped = strip_lang(stripped)
        out.bootstrap_output(fmt)
        bootstrap(flag)
        return super().main(args=stripped, **kwargs)


app = typer.Typer(
    name="acpw",
    cls=LocaleGroup,
    help="One WebSocket, many agents. Host plans; workers execute.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    add_completion=True,
)


def fail(exc: Exception) -> None:
    if isinstance(exc, AcpwError):
        out.emit(exc.payload, code=1)
    out.emit(ErrorResponse(error=str(exc)), code=1)


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
                error=t(
                    "worker {name} has no stdio adapter and cannot be pooled; drop --pool",
                    name=name,
                ),
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
        out.emit(version_payload())
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
    _lang: Annotated[
        str | None,
        typer.Option(
            "--lang",
            "-L",
            help="CLI help language. Overrides ACPW_LANG and the saved config.",
        ),
    ] = None,
    _json: Annotated[
        bool,
        typer.Option("--json", help="Write JSON instead of markdown."),
    ] = False,
    _format: Annotated[
        str | None,
        typer.Option(
            "--format",
            help=(
                "Output format: markdown (default) or json. "
                "Overrides ACPW_OUTPUT and the saved config."
            ),
        ),
    ] = None,
) -> None:
    """One WebSocket, many agents. Host plans; workers execute."""


@app.command("version")
def cmd_version() -> None:
    """Print the installed acpw version."""
    out.emit(version_payload())


@app.command("ls")
@app.command("status", hidden=True)
@app.command("discover", hidden=True)
def cmd_ls() -> None:
    """List workers and the shared WebSocket."""
    out.emit(status())


@app.command("doctor")
def cmd_doctor() -> None:
    """Check adapter binaries on PATH."""
    out.emit(doctor())


@app.command("selfcheck")
def cmd_selfcheck(
    live: Annotated[
        bool,
        typer.Option("--live/--no-live", help="Dispatch to a throwaway mock worker."),
    ] = True,
) -> None:
    """Verify the installation end to end. Exits 1 if any check fails."""
    result = run_selfcheck(live=live)
    out.emit(result, code=0 if result.ok else 1)


@app.command("add")
def cmd_add(
    name: Annotated[str, typer.Argument(help="Registry name for this worker.")],
    url: Annotated[str | None, typer.Option(help="ws://127.0.0.1:PORT/ws?server-key=...")] = None,
    bind: Annotated[
        str | None,
        typer.Option(help="host:port to listen on when this CLI starts the worker."),
    ] = None,
    kind: Annotated[str | None, typer.Option(help="grok, claude, codex, cursor, or mock.")] = None,
) -> None:
    """Register a worker or a manual websocket URL."""
    try:
        out.emit(add(WorkerCreateParams(name=name, kind=kind, url=url, bind=bind)))
    except Exception as exc:
        fail(exc)


@app.command("rm")
def cmd_rm(name: Annotated[str, typer.Argument(help="Registry name to unregister.")]) -> None:
    """Unregister a worker."""
    try:
        out.emit(rm(name))
    except Exception as exc:
        fail(exc)


@app.command("up")
@app.command("start", hidden=True)
def cmd_up(
    names: Annotated[
        list[str] | None,
        typer.Argument(help="Workers to pre-warm on the pool. Omit to start the socket only."),
    ] = None,
    cwd: Annotated[
        Path | None, typer.Option(help="Working directory for pre-warmed workers.")
    ] = None,
    timeout: Annotated[
        float, typer.Option(help="Seconds to wait for the socket and children to come up.")
    ] = 45,
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
            out.emit(
                pool_up(
                    workers=list(names) if names else None,
                    cwd=str(cwd) if cwd else None,
                    timeout=timeout,
                )
            )
            return
        if not names:
            out.emit(ErrorResponse(error=t("--no-pool needs a worker name")), code=1)
        for name in names:
            out.emit(start(name, cwd=str(cwd) if cwd else None, timeout=timeout))
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
                out.emit(ErrorResponse(error=t("--no-pool needs a worker name")), code=1)
            out.emit(stop(name))
            return
        if name is None:
            out.emit(pool_down())
            return
        out.emit(pool_stop_worker(name))
    except Exception as exc:
        fail(exc)


@app.command("ping")
def cmd_ping(
    name: Annotated[str, typer.Argument(help="Worker to handshake with.")],
    pool: Annotated[
        bool | None,
        typer.Option("--pool/--no-pool", help="Default: the shared WebSocket, for stdio workers."),
    ] = None,
) -> None:
    """ACP initialize against a live worker."""
    try:
        require_dispatchable(name)
        via_pool = use_pool(name, url=None, choice=pool)
        out.emit(pool_ping(name) if via_pool else ping(name))
    except Exception as exc:
        fail(exc)


@app.command("run")
@app.command("exec", hidden=True)
def cmd_run(
    name: Annotated[str, typer.Argument(help="Worker to dispatch to.")],
    prompt: Annotated[
        str | None,
        typer.Option("-p", help="Prompt text. Mutually exclusive with --prompt-file."),
    ] = None,
    prompt_file: Annotated[
        Path | None,
        typer.Option("-f", "--prompt-file", help="Read the prompt from this file."),
    ] = None,
    cwd: Annotated[Path | None, typer.Option(help="Working directory for the session.")] = None,
    session_id: Annotated[
        str | None,
        typer.Option(help="Resume this session instead of opening a new one."),
    ] = None,
    url: Annotated[
        str | None, typer.Option(help="Connect to this websocket and skip the pool.")
    ] = None,
    timeout: Annotated[
        float, typer.Option(help="Seconds to wait for the agent to finish the turn.")
    ] = 600,
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
        out.emit(ErrorResponse(error=t("empty prompt")), code=1)
    params = ExecParams(
        name=name,
        prompt=text or "",
        cwd=str((cwd or Path.cwd()).resolve()),
        session_id=session_id,
        url=url,
        timeout=timeout,
    )
    try:
        require_dispatchable(name)
        via_pool = use_pool(name, url=url, choice=pool)
        out.emit(pool_run(params) if via_pool else run(params))
    except Exception as exc:
        fail(exc)


@app.command("stdio")
def cmd_stdio(
    name: Annotated[str, typer.Argument(help="Registry worker this process is bound to.")],
    url: Annotated[
        str | None, typer.Option(help="Connect to this websocket and skip the pool.")
    ] = None,
) -> None:
    """Speak ACP over stdin/stdout, bound to one pooled worker."""
    raise SystemExit(run_stdio(name, url=url))


@app.command("install")
def cmd_install() -> None:
    """Register bash completion for this user."""
    out.emit(install_shell())


@app.command("uninstall")
def cmd_uninstall(
    purge: Annotated[
        bool, typer.Option(help="Also stop workers and delete registry and state.")
    ] = False,
) -> None:
    """Remove bash completion. Does not uninstall the uv tool or skill."""
    out.emit(uninstall_shell(purge=purge))


def emit_lang() -> None:
    state = current()
    out.emit(
        LangResponse(
            lang=state.lang,
            saved=state.saved,
            source=state.source,
            supported=list(SUPPORTED),
        )
    )


lang_app = typer.Typer(
    name="lang",
    help="Show or save the CLI language.",
    invoke_without_command=True,
    no_args_is_help=False,
    pretty_exceptions_enable=False,
)
app.add_typer(lang_app)


@lang_app.callback(invoke_without_command=True)
def lang_root(ctx: typer.Context) -> None:
    """Show or save the CLI language."""
    if ctx.invoked_subcommand is None:
        emit_lang()


@lang_app.command("get")
def cmd_lang_get() -> None:
    """Print the current CLI language."""
    emit_lang()


@lang_app.command("set")
def cmd_lang_set(
    lang: Annotated[
        str,
        typer.Argument(help="Language to save: zh-CN, en-US, or zh-TW."),
    ],
) -> None:
    """Save the CLI language."""
    chosen = normalize(lang)
    if chosen is None:
        out.emit(
            ErrorResponse(
                error=t(
                    "unsupported language {value}; choose {supported}",
                    value=lang,
                    supported=", ".join(SUPPORTED),
                ),
                known=list(SUPPORTED),
            ),
            code=1,
        )
        return
    save_lang(chosen)
    apply(LangState(lang=chosen, source="config", saved=chosen))
    emit_lang()


def emit_output() -> None:
    state = out.current()
    out.emit(
        OutputResponse(
            output=state.format,
            saved=state.saved,
            source=state.source,
            supported=list(out.SUPPORTED),
        )
    )


output_app = typer.Typer(
    name="output",
    help="Show or save the CLI output format.",
    invoke_without_command=True,
    no_args_is_help=False,
    pretty_exceptions_enable=False,
)
app.add_typer(output_app)


@output_app.callback(invoke_without_command=True)
def output_root(ctx: typer.Context) -> None:
    """Show or save the CLI output format."""
    if ctx.invoked_subcommand is None:
        emit_output()


@output_app.command("get")
def cmd_output_get() -> None:
    """Print the current CLI output format."""
    emit_output()


@output_app.command("set")
def cmd_output_set(
    fmt: Annotated[
        str,
        typer.Argument(help="Format to save: markdown or json."),
    ],
) -> None:
    """Save the CLI output format."""
    chosen = out.normalize(fmt)
    if chosen is None:
        out.emit(
            ErrorResponse(
                error=t(
                    "unsupported output format {value}; choose {supported}",
                    value=fmt,
                    supported=", ".join(out.SUPPORTED),
                ),
                known=list(out.SUPPORTED),
            ),
            code=1,
        )
        return
    out.save_output(chosen)
    out.apply(out.OutputState(format=chosen, source="config", saved=chosen))
    emit_output()


def emit_allow() -> None:
    out.emit(allow_policy.show())


allow_app = typer.Typer(
    name="allow",
    help="Show or save the kinds this machine may dispatch to.",
    invoke_without_command=True,
    no_args_is_help=False,
    pretty_exceptions_enable=False,
)
app.add_typer(allow_app)


@allow_app.callback(invoke_without_command=True)
def allow_root(ctx: typer.Context) -> None:
    """Show or save the kinds this machine may dispatch to."""
    if ctx.invoked_subcommand is None:
        emit_allow()


@allow_app.command("get")
def cmd_allow_get() -> None:
    """Print the allowed worker kinds."""
    emit_allow()


@allow_app.command("set")
def cmd_allow_set(
    kinds: Annotated[
        list[str],
        typer.Argument(help="Kinds to allow, such as grok or cursor."),
    ],
) -> None:
    """Replace the allow list and save it."""
    try:
        out.emit(allow_policy.set_kinds(kinds))
    except Exception as exc:
        fail(exc)


@allow_app.command("add")
def cmd_allow_add(
    kinds: Annotated[
        list[str],
        typer.Argument(help="Kinds to add."),
    ],
) -> None:
    """Add kinds to the allow list."""
    try:
        out.emit(allow_policy.add_kinds(kinds))
    except Exception as exc:
        fail(exc)


@allow_app.command("rm")
def cmd_allow_rm(
    kinds: Annotated[
        list[str],
        typer.Argument(help="Kinds to remove."),
    ],
) -> None:
    """Remove kinds from the allow list."""
    try:
        out.emit(allow_policy.remove_kinds(kinds))
    except Exception as exc:
        fail(exc)


def emit_sessions() -> None:
    out.emit(pool_sessions())


sessions_app = typer.Typer(
    name="sessions",
    help="List or delete pool sessions.",
    invoke_without_command=True,
    no_args_is_help=False,
    pretty_exceptions_enable=False,
)
app.add_typer(sessions_app)


@sessions_app.callback(invoke_without_command=True)
def sessions_root(ctx: typer.Context) -> None:
    """List or delete pool sessions."""
    if ctx.invoked_subcommand is None:
        try:
            emit_sessions()
        except Exception as exc:
            fail(exc)


@sessions_app.command("list")
def cmd_sessions_list() -> None:
    """List pool sessions."""
    try:
        emit_sessions()
    except Exception as exc:
        fail(exc)


@sessions_app.command("rm")
def cmd_sessions_rm(
    session_id: Annotated[str, typer.Argument(help="Public session id to delete.")],
) -> None:
    """Delete a pool session."""
    try:
        out.emit(pool_session_delete(session_id))
    except Exception as exc:
        fail(exc)


@sessions_app.command("prune")
def cmd_sessions_prune() -> None:
    """Delete every pool session that is not held."""
    try:
        out.emit(pool_sessions_prune())
    except Exception as exc:
        fail(exc)


pool_app = typer.Typer(
    name="pool",
    help="One resident daemon, one port, many children.",
    no_args_is_help=True,
)
app.add_typer(pool_app)


@pool_app.command("up")
def cmd_pool_up(
    bind: Annotated[str | None, typer.Option(help="Bind host:port for the pool daemon.")] = None,
    worker: Annotated[list[str] | None, typer.Option(help="Pre-warm these workers.")] = None,
    cwd: Annotated[
        Path | None, typer.Option(help="Working directory for pre-warmed workers.")
    ] = None,
    timeout: Annotated[
        float, typer.Option(help="Seconds to wait for the socket and children to come up.")
    ] = 45,
) -> None:
    """Start the pool daemon if it is not live."""
    try:
        out.emit(
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
    out.emit(pool_down())


@pool_app.command("ls")
@pool_app.command("status", hidden=True)
def cmd_pool_ls() -> None:
    """Pool liveness, children, and session counts."""
    out.emit(pool_status())


@app.command("daemon", hidden=True)
def cmd_daemon(
    secret_file: Annotated[Path, typer.Option(help="File that holds the server-key.")],
    bind: Annotated[str, typer.Option(help="Listen address host:port.")] = DEFAULT_POOL_BIND,
) -> None:
    """Internal multiplexing daemon. Started by `acpw up`."""
    run_daemon(bind, str(secret_file))


@app.command("gateway", hidden=True)
def cmd_gateway(
    name: Annotated[str, typer.Option(help="Worker name for this child.")],
    bind: Annotated[str, typer.Option(help="Listen address host:port.")],
    secret_file: Annotated[Path, typer.Option(help="File that holds the server-key.")],
    stdio_json: Annotated[str, typer.Option(help="JSON array of the stdio argv.")],
    cwd: Annotated[str, typer.Option(help="Working directory for the child.")],
) -> None:
    """Internal stdio-to-websocket bridge. Started by `acpw up --no-pool`."""
    run_gateway(name, bind, str(secret_file), json.loads(stdio_json), cwd)
