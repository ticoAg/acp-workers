from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass

from acpw.adapters import ADAPTERS
from acpw.io import load_json, save_json
from acpw.paths import config_file
from acpw.types.allow import AllowResponse


@dataclass(frozen=True)
class AllowState:
    allow: list[str]
    source: str
    saved: list[str] | None
    known: list[str]


def known_kinds(extra: Iterable[str] | None = None) -> list[str]:
    kinds = set(ADAPTERS)
    if extra:
        kinds.update(kind for kind in extra if kind)
    return sorted(kinds)


def default_kinds(extra: Iterable[str] | None = None) -> list[str]:
    kinds = {kind for kind, spec in ADAPTERS.items() if not spec.hidden}
    if extra:
        for kind in extra:
            if not kind:
                continue
            spec = ADAPTERS.get(kind)
            if spec is None or not spec.hidden:
                kinds.add(kind)
    return sorted(kinds)


def _tokens(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        token = item.strip()
        if not token:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(token)
    return sorted(out)


def saved_allow() -> list[str] | None:
    raw = load_json(config_file(), None)
    if not isinstance(raw, dict) or "allow" not in raw:
        return None
    return _tokens(raw.get("allow"))


def save_allow(kinds: list[str]) -> None:
    path = config_file()
    raw = load_json(path, {})
    if not isinstance(raw, dict):
        raw = {}
    raw["allow"] = sorted(set(kinds))
    save_json(path, raw)


def parse_env(value: str | None) -> list[str] | None:
    if value is None or not value.strip():
        return None
    return _tokens([part for part in value.split(",")])


def canonicalize(tokens: Iterable[str], known: Iterable[str]) -> tuple[list[str], list[str]]:
    mapping = {kind.lower(): kind for kind in known}
    resolved: list[str] = []
    unknown: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        raw = token.strip()
        if not raw:
            continue
        kind = mapping.get(raw.lower())
        if kind is None:
            unknown.append(raw)
            continue
        key = kind.lower()
        if key in seen:
            continue
        seen.add(key)
        resolved.append(kind)
    return sorted(resolved), unknown


def current(
    *,
    extra: Iterable[str] | None = None,
    environ: dict[str, str] | None = None,
) -> AllowState:
    env = os.environ if environ is None else environ
    extra_list = [kind for kind in extra or [] if kind]
    known = known_kinds(extra_list)
    saved = saved_allow()
    env_kinds = parse_env(env.get("ACPW_ALLOW"))
    if env_kinds is not None:
        resolved, _unknown = canonicalize(env_kinds, known)
        allow = resolved or env_kinds
        return AllowState(allow=allow, source="env", saved=saved, known=known)
    if saved is not None:
        resolved, _unknown = canonicalize(saved, known)
        return AllowState(allow=resolved or saved, source="config", saved=saved, known=known)
    return AllowState(allow=default_kinds(extra_list), source="default", saved=None, known=known)


def kind_allowed(kind: str, *, extra: Iterable[str] | None = None) -> bool:
    spec = ADAPTERS.get(kind)
    if spec is not None and spec.hidden:
        return True
    return kind in current(extra=extra).allow


def resolve_tokens(
    tokens: Iterable[str],
    *,
    extra: Iterable[str] | None = None,
    aliases: dict[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    extra_list = [kind for kind in extra or [] if kind]
    known = known_kinds(extra_list)
    mapping = {kind.lower(): kind for kind in known}
    if aliases:
        for name, kind in aliases.items():
            mapping.setdefault(name.lower(), mapping.get(kind.lower(), kind))
    expanded: list[str] = []
    unknown: list[str] = []
    for token in tokens:
        raw = token.strip()
        if not raw:
            continue
        kind = mapping.get(raw.lower())
        if kind is None:
            unknown.append(raw)
            continue
        expanded.append(kind)
    resolved, leftover = canonicalize(expanded, known)
    unknown.extend(leftover)
    return resolved, unknown


def _context() -> tuple[list[str], dict[str, str]]:
    from acpw.registry import registry_kinds, worker_kind_aliases

    return registry_kinds(), worker_kind_aliases()


def _unknown(unknown: list[str], known: list[str]) -> None:
    from acpw.i18n import t
    from acpw.registry import AcpwError
    from acpw.types import ErrorResponse

    raise AcpwError(
        ErrorResponse(
            error=t(
                "unknown kind {kind}; choose {supported}",
                kind=", ".join(unknown),
                supported=", ".join(known),
            ),
            known=list(known),
        )
    )


def show() -> AllowResponse:
    extra, _aliases = _context()
    state = current(extra=extra)
    return AllowResponse(
        allow=state.allow, saved=state.saved, source=state.source, known=state.known
    )


def set_kinds(tokens: list[str]) -> AllowResponse:
    extra, aliases = _context()
    resolved, unknown = resolve_tokens(tokens, extra=extra, aliases=aliases)
    if unknown:
        _unknown(unknown, known_kinds(extra))
    save_allow(resolved)
    return show()


def add_kinds(tokens: list[str]) -> AllowResponse:
    extra, aliases = _context()
    resolved, unknown = resolve_tokens(tokens, extra=extra, aliases=aliases)
    if unknown:
        _unknown(unknown, known_kinds(extra))
    state = current(extra=extra)
    save_allow(sorted(set(state.allow) | set(resolved)))
    return show()


def remove_kinds(tokens: list[str]) -> AllowResponse:
    extra, aliases = _context()
    resolved, unknown = resolve_tokens(tokens, extra=extra, aliases=aliases)
    if unknown:
        _unknown(unknown, known_kinds(extra))
    state = current(extra=extra)
    save_allow(sorted(set(state.allow) - set(resolved)))
    return show()
