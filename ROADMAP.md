# ACP Workers 路线图

本仓库做一件事：把本机多个 ACP agent（grok / claude / codex / cursor）挂在**一条** WebSocket 后面。Host 规划、派发、验收；worker 只执行。

官方 ACP（[v1](https://agentclientprotocol.com/protocol/v1/overview)）已经够用。mux **不再发明传输或 RPC 方言**。相对 `grok -p`，本机 hop 不是瓶颈，也不去做“更快的 JSON-RPC”。

线路契约：[docs/pool-protocol.md](docs/pool-protocol.md)。实施约束：[docs/research-plan.md](docs/research-plan.md)。代码是 SSOT；文档与代码不一致时，改文档。

## 现在（0.6.7）

- 一条 pool daemon（默认 `0.0.0.0:48190`），底下 stdio children
- 公开 `sessionId`（`acpw-s` + 16 hex），L1 连接 / L2 child / L3 daemon 可续
- Host 用 `_meta.worker` 选 agent；`acpw stdio NAME` 给编辑器补上该字段
- `worker/list|up|down` 是 pool 控制面（未加 `_` 前缀；改名会破坏 CLI，见以后）
- `initialize` 广告 `sessionCapabilities.list` / `delete`
- 官方 [`session/list`](https://agentclientprotocol.com/rfds/session-list) 与 [`session/delete`](https://agentclientprotocol.com/protocol/v1/session-delete)：daemon 自己应答；stdio 按 worker 过滤；占用中拒绝删除
- CLI：`acpw sessions` / `sessions list` / `sessions rm ID` / `sessions prune`（无自动 TTL）
- `docs/pool-protocol.md` 与 daemon 方法名对齐；契约测试锁 initialize、路由、文档用词

## 下一步

本轮协议切片已随 0.6.7 发出。以后见下表。

## 以后

| 项 | 为什么还没做 |
| --- | --- |
| `_worker/*` 别名 | ACP 要求扩展方法以下划线开头。现有 `worker/*` 已出货；先广告 `_meta` 能力再加别名 |
| Host 侧 `fs/*` / `terminal/*` | daemon 对 child 声明关闭，MuxClient 回 `-32601`。编辑器广告的 fs 到不了 child |
| ACP v2 | `loadSession` 等会变；等规范稳定再跟 |
| 可选 session TTL | 必须显式、默认可关，且不能破坏 L3 |
| 持久 CLI 连接 | 每次 `acpw run` 新开一条 WS；省的是进程启动，不是 hop |
| hop/child/模型分段计时 | 观测，不改协议 |

## 明确非目标

- 新的传输或新的 RPC 方言
- 优化 localhost WebSocket / stdio 转发延迟
- 把 worker 的自我报告当成验收
