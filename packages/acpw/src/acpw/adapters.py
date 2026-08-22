from __future__ import annotations

from acpw.types import Adapter, TransportKind

ADAPTERS: dict[str, Adapter] = {
    "grok": Adapter(
        kind="grok",
        transport=TransportKind.native_ws,
        default_bind="0.0.0.0:48191",
        binary="grok",
        # Same shape acpx uses (`grok agent stdio`). --no-leader keeps each child its
        # own backend; --always-approve matches `acpw up grok` / `--no-pool`.
        stdio_argv=["grok", "agent", "--always-approve", "--no-leader", "stdio"],
        notes="Stdio child on the shared WebSocket; `acpw up grok --no-pool` still starts serve.",
    ),
    "claude": Adapter(
        kind="claude",
        transport=TransportKind.stdio_bridge,
        default_bind="0.0.0.0:48192",
        binary="npx",
        stdio_argv=["npx", "-y", "@agentclientprotocol/claude-agent-acp"],
        notes="Official ACP adapter wrapping Claude Code stdio.",
    ),
    "codex": Adapter(
        kind="codex",
        transport=TransportKind.stdio_bridge,
        default_bind="0.0.0.0:48193",
        binary="npx",
        stdio_argv=["npx", "-y", "@agentclientprotocol/codex-acp"],
        notes="Official ACP adapter wrapping Codex CLI stdio.",
    ),
    "cursor": Adapter(
        kind="cursor",
        transport=TransportKind.stdio_bridge,
        default_bind="0.0.0.0:48194",
        binary="cursor-agent",
        stdio_argv=["cursor-agent", "acp"],
        notes="Cursor Agent CLI ACP stdio.",
    ),
    "mock": Adapter(
        kind="mock",
        transport=TransportKind.stdio_bridge,
        default_bind="0.0.0.0:48199",
        hidden=True,
        stdio_argv=["python3", "-m", "acpw.agents.echo"],
        notes="In-package echo agent for tests.",
    ),
}


def resolve_stdio_argv(entry_argv: list[str] | None, spec: Adapter | None) -> list[str]:
    """The command the pool (or a gateway) would spawn. Empty means not poolable."""
    if entry_argv:
        return list(entry_argv)
    if spec and spec.stdio_argv:
        return list(spec.stdio_argv)
    return []


PROCESS_NEEDLES = {
    "grok": "agent serve",
    "claude": "claude-agent-acp",
    "codex": "codex-acp",
    "cursor": "cursor-agent",
}
