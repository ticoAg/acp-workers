from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any

import typer
from pydantic import BaseModel

from acpw.io import load_json, save_json
from acpw.paths import config_file
from acpw.types import ExecResponse, SelfCheckResponse, WorkerStatusList

SUPPORTED = ("markdown", "json")
DEFAULT = "markdown"

_ALIASES = {
    "md": "markdown",
    "markdown": "markdown",
    "text": "markdown",
    "json": "json",
}


@dataclass(frozen=True)
class OutputState:
    format: str
    source: str
    saved: str | None


_state = OutputState(format=DEFAULT, source="default", saved=None)


def current() -> OutputState:
    return _state


def normalize(value: str | None) -> str | None:
    if not value:
        return None
    return _ALIASES.get(value.strip().lower())


def saved_output() -> str | None:
    raw = load_json(config_file(), None)
    if not isinstance(raw, dict):
        return None
    return normalize(raw.get("output") if isinstance(raw.get("output"), str) else None)


def save_output(fmt: str) -> None:
    path = config_file()
    raw = load_json(path, {})
    if not isinstance(raw, dict):
        raw = {}
    raw["output"] = fmt
    save_json(path, raw)


def strip_output(argv: list[str]) -> tuple[str | None, list[str]]:
    flag: str | None = None
    out: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--json":
            flag = "json"
            i += 1
            continue
        if arg == "--format" and i + 1 < len(argv) and not argv[i + 1].startswith("-"):
            flag = argv[i + 1]
            i += 2
            continue
        if arg.startswith("--format="):
            flag = arg.split("=", 1)[1]
            i += 1
            continue
        out.append(arg)
        i += 1
    return flag, out


def resolve(*, flag: str | None = None, environ: dict[str, str] | None = None) -> OutputState:
    env = os.environ if environ is None else environ
    saved = saved_output()
    if flag is not None:
        fmt = normalize(flag)
        if fmt:
            return OutputState(format=fmt, source="flag", saved=saved)
    env_fmt = normalize(env.get("ACPW_OUTPUT"))
    if env_fmt:
        return OutputState(format=env_fmt, source="env", saved=saved)
    if saved:
        return OutputState(format=saved, source="config", saved=saved)
    return OutputState(format=DEFAULT, source="default", saved=saved)


def apply(state: OutputState) -> None:
    global _state
    _state = state


def bootstrap_output(flag: str | None) -> None:
    apply(resolve())
    if flag is None:
        return
    fmt = normalize(flag)
    if fmt is None:
        from acpw.i18n import t
        from acpw.types import ErrorResponse

        sys.stdout.write(
            dumps(
                ErrorResponse(
                    error=t(
                        "unsupported output format {value}; choose {supported}",
                        value=flag,
                        supported=", ".join(SUPPORTED),
                    ),
                    known=list(SUPPORTED),
                )
            )
            + "\n"
        )
        raise SystemExit(1)
    apply(resolve(flag=flag))


def emit(model: BaseModel, *, code: int = 0) -> None:
    typer.echo(dumps(model))
    if code:
        raise typer.Exit(code)


def dumps(model: BaseModel) -> str:
    if _state.format == "json":
        return model.model_dump_json()
    return render(model)


def render(model: BaseModel) -> str:
    if isinstance(model, ExecResponse):
        return _render_exec(model)
    if isinstance(model, WorkerStatusList):
        return _render_ls(model)
    if isinstance(model, SelfCheckResponse):
        return _render_selfcheck(model)
    return _render_generic(model)


def _render_generic(model: BaseModel) -> str:
    data = model.model_dump(mode="json")
    lines, skip = _status_lines(data)
    lines.extend(_render_mapping(data, skip=skip, depth=2))
    return _join(lines)


def _render_exec(model: ExecResponse) -> str:
    data = model.model_dump(mode="json")
    text = data.pop("text", None)
    lines, skip = _status_lines(data)
    lines.extend(_render_mapping(data, skip=skip, depth=2))
    if isinstance(text, str) and text.strip():
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(text.rstrip("\n"))
    return _join(lines)


def _render_ls(model: WorkerStatusList) -> str:
    data = model.model_dump(mode="json")
    lines, _ = _status_lines(data)
    pool = data.get("pool")
    if isinstance(pool, dict) and not _omit(pool):
        lines.append("")
        lines.append("## pool")
        lines.append("")
        lines.extend(_render_mapping(pool, skip={"ok"}, depth=3))
    lines.append("")
    lines.append("## workers")
    lines.append("")
    registry = data.get("registry")
    if registry:
        lines.append(f"registry: {_md_value(registry)}")
        lines.append("")
    workers = data.get("workers") or []
    if isinstance(workers, list) and workers and _is_table(workers):
        lines.extend(_table(workers))
    else:
        lines.append("(none)")
    extras = {
        key: data[key] for key in ("listening_defaults", "processes") if not _omit(data.get(key))
    }
    if extras:
        lines.append("")
        lines.extend(_render_mapping(extras, skip=set(), depth=2))
    return _join(lines)


def _render_selfcheck(model: SelfCheckResponse) -> str:
    data = model.model_dump(mode="json")
    lines, _ = _status_lines(data)
    version = data.get("version")
    if version:
        lines.append(f"version: {_md_value(version)}")
    failed = data.get("failed") or []
    warned = data.get("warned") or []
    if failed:
        lines.append(f"failed: {_join_scalars(failed)}")
    if warned:
        lines.append(f"warned: {_join_scalars(warned)}")
    checks = data.get("checks") or []
    if isinstance(checks, list) and checks and _is_table(checks):
        lines.append("")
        lines.append("## checks")
        lines.append("")
        lines.extend(_table(checks))
    return _join(lines)


def _status_lines(data: dict[str, Any]) -> tuple[list[str], set[str]]:
    skip: set[str] = set()
    lines: list[str] = []
    if "ok" in data:
        skip.add("ok")
        lines.append("ok" if data["ok"] else "ok: false")
    error = data.get("error")
    if error:
        skip.add("error")
        lines.append(f"error: {error}")
    return lines, skip


def _render_mapping(data: dict[str, Any], *, skip: set[str], depth: int) -> list[str]:
    lines: list[str] = []
    for key, value in data.items():
        if key in skip or _omit(value):
            continue
        if _is_table(value):
            lines.append("")
            lines.append(f"{'#' * depth} {key}")
            lines.append("")
            lines.extend(_table(value))
            lines.append("")
            continue
        if isinstance(value, dict):
            lines.append("")
            lines.append(f"{'#' * depth} {key}")
            lines.append("")
            lines.extend(_render_mapping(value, skip=set(), depth=min(depth + 1, 6)))
            lines.append("")
            continue
        if isinstance(value, list):
            lines.extend(_render_list(key, value))
            continue
        lines.append(f"{key}: {_md_value(value)}")
    return lines


def _render_list(key: str, value: list[Any]) -> list[str]:
    if _all_scalars(value) and any(
        isinstance(item, str) and (" " in item or len(item) > 48) for item in value
    ):
        return [f"{key}:", *[f"- {item}" for item in value]]
    if _all_scalars(value):
        return [f"{key}: {_join_scalars(value)}"]
    return [
        f"{key}:",
        "```json",
        json.dumps(value, ensure_ascii=False, indent=2),
        "```",
    ]


def _table(rows: list[dict[str, Any]]) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                keys.append(key)
    keys = [key for key in keys if any(not _blank(row.get(key)) for row in rows)]
    if not keys:
        return ["(none)"]
    header = "| " + " | ".join(keys) + " |"
    rule = "| " + " | ".join("---" for _ in keys) + " |"
    body = ["| " + " | ".join(_md_cell(row.get(key)) for key in keys) + " |" for row in rows]
    return [header, rule, *body]


def _omit(value: object) -> bool:
    if _blank(value):
        return True
    return isinstance(value, dict) and bool(value) and all(_omit(item) for item in value.values())


def _blank(value: object) -> bool:
    return value is None or value == [] or value == {}


def _is_table(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, dict) for item in value)


def _all_scalars(value: list[Any]) -> bool:
    return all(not isinstance(item, (dict, list)) for item in value)


def _join_scalars(value: list[Any]) -> str:
    return ", ".join(_md_value(item) for item in value)


def _md_value(value: object) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return ""
    text = str(value)
    if "/" in text or "://" in text:
        return f"`{text}`"
    return text


def _md_cell(value: object) -> str:
    text = _md_value(value).replace("\n", " ").replace("|", "\\|")
    return text


def _join(lines: list[str]) -> str:
    out: list[str] = []
    prev_blank = True
    for line in lines:
        blank = line == ""
        if blank and prev_blank:
            continue
        out.append(line)
        prev_blank = blank
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)
