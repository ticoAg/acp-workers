from __future__ import annotations

from acpw.types import Adapter, TransportKind

ADAPTERS: dict[str, Adapter] = {
    "grok": Adapter(
        kind="grok",
        transport=TransportKind.native_ws,
        default_bind="127.0.0.1:48191",
        binary="grok",
        notes="Native ACP WebSocket via grok agent serve.",
    ),
    "claude": Adapter(
        kind="claude",
        transport=TransportKind.stdio_bridge,
        default_bind="127.0.0.1:48192",
        binary="npx",
        stdio_argv=["npx", "-y", "@agentclientprotocol/claude-agent-acp"],
        notes="Official ACP adapter wrapping Claude Code stdio.",
    ),
    "codex": Adapter(
        kind="codex",
        transport=TransportKind.stdio_bridge,
        default_bind="127.0.0.1:48193",
        binary="npx",
        stdio_argv=["npx", "-y", "@agentclientprotocol/codex-acp"],
        notes="Official ACP adapter wrapping Codex CLI stdio.",
    ),
    "cursor": Adapter(
        kind="cursor",
        transport=TransportKind.stdio_bridge,
        default_bind="127.0.0.1:48194",
        binary="cursor-agent",
        stdio_argv=["cursor-agent", "acp"],
        notes="Cursor Agent CLI ACP stdio.",
    ),
    "mock": Adapter(
        kind="mock",
        transport=TransportKind.stdio_bridge,
        default_bind="127.0.0.1:48199",
        hidden=True,
        stdio_argv=["python3", "-m", "acpw.agents.echo"],
        notes="In-package echo agent for tests.",
    ),
}

PROCESS_NEEDLES = {
    "grok": "agent serve",
    "claude": "claude-agent-acp",
    "codex": "codex-acp",
    "cursor": "cursor-agent",
}
