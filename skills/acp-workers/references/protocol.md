# ACP Workers protocol

## URL

All workers, native or bridged:

```
ws://127.0.0.1:<port>/ws?server-key=<secret>
```

- Missing/wrong key on `/ws` → HTTP `401`.
- Bridged workers also serve `GET /health` → JSON `{ok, name, transport, child_alive, child_pid}`.
- Grok native serve has no `/health`; a `401` on `/ws` without a key is the liveness signal.

## ACP on the socket

Text WebSocket frames, one JSON-RPC object per frame (same methods as ACP stdio):

1. `initialize`
2. `authenticate` when `authMethods` is non-empty (`cached_token` for Grok, `cursor_login` for Cursor)
3. `session/new` `{cwd, mcpServers: [], _meta: {yoloMode: true}}` or `session/load`
4. `session/prompt` `{sessionId, prompt: [{type:"text", text}]}`
5. `session/update` notifications, then the prompt result `{stopReason}`

`exec` answers `session/request_permission` with `allow-once`. It does not implement client `fs/*`.

## Who inherits what (Grok native)

`start grok` is `grok agent --always-approve --no-leader serve`. Same process as the TUI for:

- `~/.grok/auth.json`
- `~/.grok/config.toml` (`permission.deny`, `permission_mode`, `[mcp_servers]`, model)
- project `AGENTS.md` / `CLAUDE.md` from `--cwd`
- skills/plugins discovered from that cwd

It does **not** inherit Cursor Auto-run. Deny rules still win over always-approve.

## Stdio bridge

Claude / Codex / Cursor have no Grok-style `serve`. Grok has both: `grok agent serve` (`acpw up grok` / `--no-pool`) and `grok agent --always-approve --no-leader stdio` (the pool child, same argv shape as acpx's `grok-build`). `acpw gateway` keeps one stdio ACP child and one in-flight WebSocket client. `initialize`/`authenticate` results are cached so the next `ping`/`run` does not re-handshake the child.

One client at a time is the limit that `acpw pool` lifts: the same children move under one daemon that serves many connections and many concurrent requests. A worker is poolable when it has a `stdio_argv`, regardless of its standalone transport. See [pool.md](pool.md).

Default binds: grok `0.0.0.0:48191`, claude `48192`, codex `48193`, cursor `48194`, pool `48190`. The listen address is `0.0.0.0`; clients dial `127.0.0.1`.

Adapter defaults (binary, `stdio_argv`, default bind) live in `packages/acpw/src/acpw/adapters.py`. Override `stdio_argv` on a registry entry when the machine uses a different binary; see [../assets/registry.example.json](../assets/registry.example.json) for the entry shape.
