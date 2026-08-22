# ACP Workers 协议

## URL

所有 worker，无论原生还是桥接：

```
ws://127.0.0.1:<port>/ws?server-key=<secret>
```

- `/ws` 上 key 缺失或错误 → HTTP `401`。
- 桥接 worker 还提供 `GET /health` → JSON `{ok, name, transport, child_alive, child_pid}`。
- Grok 原生 serve 没有 `/health`；不带 key 打 `/ws` 得到 `401` 就是探活信号。

## Socket 上的 ACP

文本 WebSocket 帧，每帧一个 JSON-RPC 对象（method 与 ACP stdio 相同）：

1. `initialize`
2. `authMethods` 非空时 `authenticate`（Grok 用 `cached_token`，Cursor 用 `cursor_login`）
3. `session/new` `{cwd, mcpServers: [], _meta: {yoloMode: true}}` 或 `session/load`
4. `session/prompt` `{sessionId, prompt: [{type:"text", text}]}`
5. `session/update` notification，然后 prompt 结果 `{stopReason}`

`exec` 用 `allow-once` 应答 `session/request_permission`。它不实现客户端 `fs/*`。

## 谁继承什么（Grok 原生）

`start grok` 即 `grok agent --always-approve --no-leader serve`。与 TUI 共用同一进程来源：

- `~/.grok/auth.json`
- `~/.grok/config.toml`（`permission.deny`、`permission_mode`、`[mcp_servers]`、model）
- 来自 `--cwd` 的项目 `AGENTS.md` / `CLAUDE.md`
- 从该 cwd 发现的 skills / plugins

它**不**继承 Cursor Auto-run。Deny 规则仍然压过 always-approve。

## Stdio 桥

Claude / Codex / Cursor 没有 Grok 那种 `serve`。Grok 两种都有：`grok agent serve`（`acpw up grok --no-pool`）和 `grok agent --always-approve --no-leader stdio`（原生 pool child，argv 形状与 acpx 的 `grok-build` 相同）。`acpw gateway` 保一个 stdio ACP child 和一条 in-flight WebSocket 客户端。`initialize` / `authenticate` 结果会缓存，下次 `ping` / `run` 不必再和 child 握手。

「同一时刻一个客户端」是共享 WebSocket 解开的限制：同样这些 children 挂在一个 daemon 下，服务多条连接和多条并发请求。Worker 有 `stdio_argv` 就能进 pool，与它独立时的 transport 无关。见 [pool.md](pool.md)。

默认 bind：grok `0.0.0.0:48191`，claude `48192`，codex `48193`，cursor `48194`，pool `48190`。监听地址是 `0.0.0.0`；客户端拨 `127.0.0.1`。

Adapter 默认值（二进制、`stdio_argv`、默认 bind）在 `packages/acpw/src/acpw/adapters.py`。本机二进制不在默认位置时，在 registry 条目上覆盖 `stdio_argv`；条目形状见 [../assets/registry.example.json](../assets/registry.example.json)。
