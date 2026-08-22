from __future__ import annotations

import inspect
import os
import re
import sys
from dataclasses import dataclass
from typing import Any

from acpw.io import load_json, save_json
from acpw.locales import CATALOGS
from acpw.paths import config_file

SUPPORTED = ("en-US", "zh-CN", "zh-TW")
DEFAULT_LANG = "en-US"

_ALIASES = {
    "en": "en-US",
    "en-us": "en-US",
    "en-latn": "en-US",
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh-hans": "zh-CN",
    "zh-sg": "zh-CN",
    "zh-tw": "zh-TW",
    "zh-hant": "zh-TW",
    "zh-hk": "zh-TW",
    "zh-mo": "zh-TW",
}

_UI_CONSTANTS = (
    ("DEPRECATED_STRING", "(deprecated) "),
    ("DEFAULT_STRING", "[default: {}]"),
    ("ENVVAR_STRING", "[env var: {}]"),
    ("REQUIRED_LONG_STRING", "[required]"),
    ("ARGUMENTS_PANEL_TITLE", "Arguments"),
    ("OPTIONS_PANEL_TITLE", "Options"),
    ("COMMANDS_PANEL_TITLE", "Commands"),
    ("ERRORS_PANEL_TITLE", "Error"),
    ("ABORTED_TEXT", "Aborted."),
    ("RICH_HELP", "Try [blue]'{command_path} {help_option}'[/] for help."),
)

_METAVARS = frozenset({"[OPTIONS]", "COMMAND [ARGS]...", "[ARGS]..."})

_CLICK_PATTERNS = (
    (
        re.compile(r"^Missing argument (?P<hint>\S.*?)(\.(?P<extra>.*))?$"),
        "Missing argument {hint}.{extra}",
    ),
    (
        re.compile(r"^Missing option (?P<hint>\S.*?)(\.(?P<extra>.*))?$"),
        "Missing option {hint}.{extra}",
    ),
    (
        re.compile(r"^Missing parameter (?P<hint>\S.*?)(\.(?P<extra>.*))?$"),
        "Missing parameter {hint}.{extra}",
    ),
    (
        re.compile(r"^No such option: (?P<name>\S+) \(Possible options: (?P<options>.+)\)$"),
        "No such option: {name} (Possible options: {options})",
    ),
    (re.compile(r"^No such option: (?P<name>.+)$"), "No such option: {name}"),
    (
        re.compile(r"^No such command (?P<name>.+)\. Did you mean (?P<suggestions>.+)\?$"),
        "No such command {name}. Did you mean {suggestions}?",
    ),
    (re.compile(r"^No such command (?P<name>.+)\.$"), "No such command {name}."),
    (
        re.compile(r"^Got unexpected extra argument\(s\) \((?P<args>.+)\)$"),
        "Got unexpected extra argument(s) ({args})",
    ),
    (
        re.compile(r"^Invalid value for (?P<hint>.+): (?P<message>.+)$"),
        "Invalid value for {hint}: {message}",
    ),
    (re.compile(r"^Invalid value: (?P<message>.+)$"), "Invalid value: {message}"),
    (
        re.compile(r"^Could not open file (?P<filename>.+): (?P<message>.+)$"),
        "Could not open file {filename}: {message}",
    ),
    (
        re.compile(r"^(?P<value>.+) is not a valid (?P<name>.+)\.$"),
        "{value} is not a valid {name}.",
    ),
    (
        re.compile(r"^(?P<shell>\S+) completion installed in (?P<path>.+)$"),
        "{shell} completion installed in {path}",
    ),
)


@dataclass(frozen=True)
class LangState:
    lang: str
    source: str
    saved: str | None


_state = LangState(lang=DEFAULT_LANG, source="default", saved=None)
_patched = False


def t(msgid: str, **kwargs: object) -> str:
    template = CATALOGS.get(_state.lang, {}).get(msgid, msgid)
    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return template


def current() -> LangState:
    return _state


def normalize(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip().replace("_", "-")
    if "." in raw:
        raw = raw.split(".", 1)[0]
    if raw in SUPPORTED:
        return raw
    return _ALIASES.get(raw.lower())


def saved_lang() -> str | None:
    raw = load_json(config_file(), None)
    if not isinstance(raw, dict):
        return None
    return normalize(raw.get("lang") if isinstance(raw.get("lang"), str) else None)


def save_lang(lang: str) -> None:
    path = config_file()
    raw = load_json(path, {})
    if not isinstance(raw, dict):
        raw = {}
    raw["lang"] = lang
    save_json(path, raw)


def strip_lang(argv: list[str]) -> tuple[str | None, list[str]]:
    flag: str | None = None
    out: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in {"--lang", "-L"} and i + 1 < len(argv) and not argv[i + 1].startswith("-"):
            flag = argv[i + 1]
            i += 2
            continue
        if arg.startswith("--lang="):
            flag = arg.split("=", 1)[1]
            i += 1
            continue
        out.append(arg)
        i += 1
    return flag, out


def resolve(*, flag: str | None = None, environ: dict[str, str] | None = None) -> LangState:
    env = os.environ if environ is None else environ
    saved = saved_lang()
    if flag is not None:
        lang = normalize(flag)
        if lang:
            return LangState(lang=lang, source="flag", saved=saved)
    env_lang = normalize(env.get("ACPW_LANG"))
    if env_lang:
        return LangState(lang=env_lang, source="env", saved=saved)
    if saved:
        return LangState(lang=saved, source="config", saved=saved)
    for key in ("LC_ALL", "LC_MESSAGES", "LANG"):
        raw = env.get(key)
        if not raw:
            continue
        tag = raw.split(".", 1)[0]
        if tag in {"C", "POSIX"}:
            continue
        system = normalize(raw)
        if system:
            return LangState(lang=system, source="system", saved=saved)
    return LangState(lang=DEFAULT_LANG, source="default", saved=saved)


def apply(state: LangState) -> None:
    global _state
    _state = state
    _apply_ui()


def bootstrap(flag: str | None) -> None:
    install_patches()
    state = resolve()
    apply(state)
    if flag is None:
        return
    lang = normalize(flag)
    if lang is None:
        from acpw.types import ErrorResponse

        sys.stdout.write(
            ErrorResponse(
                error=t(
                    "unsupported language {value}; choose {supported}",
                    value=flag,
                    supported=", ".join(SUPPORTED),
                ),
                known=list(SUPPORTED),
            ).model_dump_json()
            + "\n"
        )
        raise SystemExit(1)
    apply(resolve(flag=flag))


def localize_click(message: str) -> str:
    exact = t(message)
    if exact != message:
        return exact
    current = message
    for _ in range(3):
        nxt = _click_pass(current)
        if nxt == current:
            return nxt
        current = nxt
    return current


def _click_pass(message: str) -> str:
    for pattern, msgid in _CLICK_PATTERNS:
        matched = pattern.fullmatch(message)
        if not matched:
            continue
        fields = {key: (value or "") for key, value in matched.groupdict().items()}
        if fields.get("message"):
            fields["message"] = localize_click(fields["message"])
        translated = t(msgid, **fields)
        if translated != msgid:
            return translated
        return message
    return message


def _apply_ui() -> None:
    try:
        from typer import rich_utils
    except ImportError:  # pragma: no cover - typer is a hard dependency
        return
    for attr, msgid in _UI_CONSTANTS:
        setattr(rich_utils, attr, t(msgid))
    usage = re.escape(t("Usage: "))
    rich_utils.OptionHighlighter.highlights[-1] = rf"(?P<usage>{usage})"
    rich_utils.highlighter = rich_utils.OptionHighlighter()


def install_patches() -> None:
    global _patched
    if _patched:
        _apply_ui()
        return
    _patched = True
    _patch_typer()
    _apply_ui()


def _patch_typer() -> None:
    import inspect as inspect_mod

    from rich.table import Table
    from typer import core as typer_core
    from typer import rich_utils
    from typer._click._compat import get_text_stderr
    from typer._click.core import Command
    from typer._click.exceptions import (
        BadParameter,
        ClickException,
        FileError,
        MissingParameter,
        NoSuchOption,
        UsageError,
    )
    from typer._click.formatting import HelpFormatter
    from typer._click.utils import echo

    orig_write_usage = HelpFormatter.write_usage

    def write_usage(
        self: HelpFormatter, prog: str, args: str = "", prefix: str | None = None
    ) -> None:
        if prefix is None:
            prefix = t("Usage: ")
        orig_write_usage(self, prog, args, prefix)

    HelpFormatter.write_usage = write_usage  # type: ignore[method-assign]

    orig_collect = Command.collect_usage_pieces

    def collect_usage_pieces(self: Command, ctx: Any) -> list[str]:
        return [_t_metavar(piece) for piece in orig_collect(self, ctx)]

    Command.collect_usage_pieces = collect_usage_pieces  # type: ignore[method-assign]

    orig_group_collect = typer_core.TyperGroup.collect_usage_pieces

    def group_collect_usage_pieces(self: Any, ctx: Any) -> list[str]:
        return [_t_metavar(piece) for piece in orig_group_collect(self, ctx)]

    typer_core.TyperGroup.collect_usage_pieces = group_collect_usage_pieces  # type: ignore[method-assign]

    orig_short = Command.get_short_help_str

    def get_short_help_str(self: Command, limit: int = 45) -> str:
        saved_help, saved_short = self.help, self.short_help
        try:
            if self.short_help:
                self.short_help = t(self.short_help)
            elif self.help:
                self.help = t(inspect_mod.cleandoc(self.help))
            return orig_short(self, limit)
        finally:
            self.help, self.short_help = saved_help, saved_short

    Command.get_short_help_str = get_short_help_str  # type: ignore[method-assign]

    orig_rich_help = rich_utils.rich_format_help

    def rich_format_help(*, obj: Any, ctx: Any, markup_mode: Any) -> None:
        restore = _translate_help_tree(obj, ctx)
        try:
            return orig_rich_help(obj=obj, ctx=ctx, markup_mode=markup_mode)
        finally:
            restore()

    rich_utils.rich_format_help = rich_format_help

    orig_add_column = Table.add_column

    def add_column(self: Table, header: Any = "", *args: Any, **kwargs: Any) -> None:
        if header == "Description":
            header = t("Description")
        orig_add_column(self, header, *args, **kwargs)

    Table.add_column = add_column  # type: ignore[method-assign]

    def _wrap_format(cls: type) -> None:
        orig = cls.format_message

        def format_message(self: Any) -> str:
            return localize_click(orig(self))

        cls.format_message = format_message  # type: ignore[method-assign]

    for cls in (ClickException, BadParameter, MissingParameter, NoSuchOption, FileError):
        _wrap_format(cls)

    def usage_show(self: UsageError, file: Any | None = None) -> None:
        if file is None:
            file = get_text_stderr()
        color = None
        hint = ""
        if self.ctx is not None and self.ctx.command.get_help_option(self.ctx) is not None:
            hint = t(
                "Try '{command_path} {help_option}' for help.\n",
                command_path=self.ctx.command_path,
                help_option=self.ctx.help_option_names[0],
            )
        if self.ctx is not None:
            color = self.ctx.color
            echo(f"{self.ctx.get_usage()}\n{hint}", file=file, color=color)
        echo(f"{t('Error')}: {self.format_message()}", file=file, color=color)

    UsageError.show = usage_show  # type: ignore[method-assign]
    orig_click_show = ClickException.show

    def click_show(self: ClickException, file: Any | None = None) -> None:
        if type(self) is not ClickException:
            orig_click_show(self, file)
            return
        if file is None:
            file = get_text_stderr()
        echo(f"{t('Error')}: {self.format_message()}", file=file, color=self.show_color)

    ClickException.show = click_show  # type: ignore[method-assign]


def _t_metavar(piece: str) -> str:
    return t(piece) if piece in _METAVARS else piece


def _translate_help_tree(obj: Any, ctx: Any) -> Any:
    saved: list[tuple[Any, str | None, str | None, list[tuple[Any, str | None]]]] = []
    seen: set[int] = set()

    def snap(cmd: Any) -> None:
        ident = id(cmd)
        if ident in seen:
            return
        seen.add(ident)
        try:
            params = list(cmd.get_params(ctx)) if ctx is not None else list(cmd.params)
        except Exception:  # noqa: BLE001 - help rendering must not crash
            params = list(getattr(cmd, "params", []))
        param_help = [(param, param.help) for param in params]
        saved.append((cmd, cmd.help, getattr(cmd, "short_help", None), param_help))
        if cmd.help:
            cmd.help = t(inspect.cleandoc(cmd.help))
        if getattr(cmd, "short_help", None):
            cmd.short_help = t(cmd.short_help)
        for param, help_text in param_help:
            if help_text:
                param.help = t(help_text)
        commands = getattr(cmd, "commands", None)
        if commands:
            for child in commands.values():
                snap(child)

    snap(obj)

    def restore() -> None:
        for cmd, help_text, short_help, params in saved:
            cmd.help = help_text
            cmd.short_help = short_help
            for param, param_help in params:
                param.help = param_help

    return restore
