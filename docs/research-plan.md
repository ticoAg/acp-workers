# Pool 协议研发计划（本轮）

给实施 agent 的约束。做完对照 [ROADMAP.md](../ROADMAP.md) 的「下一步」。

## SSOT

**代码是 SSOT。** 以 [`packages/acpw/src/acpw/daemon.py`](../packages/acpw/src/acpw/daemon.py) 为准：

| 项 | 代码里的真实值 |
| --- | --- |
| 开 session | `session/new`、`session/load` |
| 路由字段 | `params._meta.worker` |
| 控制面 | `worker/list`、`worker/up`、`worker/down` |
| 握手 | `initialize` / `authenticate` |
| 公开 id | `acpw-s` + 16 位 hex |
| initialize 字段 | `protocolVersion`、`agentCapabilities.loadSession`、`promptCapabilities`、`authMethods`、`agentInfo` |
| 未知 method | `-32602` `no route: <method>` |
| WebSocket | `ws://127.0.0.1:<port>/ws?server-key=<secret>` |
| 探活 | `GET /health` |
| daemon 入口 | `run_daemon(bind, secret_file)` |
| 客户端 | `MuxClient` |

文档、skill、CHANGELOG 去就这些名字。**不要**为了迁就旧文档把 RPC 改成 `session/new` 或 `_meta.worker`。

新方法跟官方 ACP，不自造顶层字段。公开 `sessionId` 永不泄漏 child native id。

## 本轮要做

### 1. 规格对齐

重写 [`docs/pool-protocol.md`](pool-protocol.md)，使方法名、错误文案、模块符号与 daemon / `pool.py` / `client.py` 一致，并补上 `session/list`、`session/delete`。

契约测试（`packages/acpw/tests/test_protocol_contract.py`）至少断言该文档含：`session/new`、`_meta.worker`、`worker/list`、`session/list`、`session/delete`。

### 2. `initialize` 广告

在现有字段上增加 `sessionCapabilities`，不要改名已有键：

```json
{
  "protocolVersion": 1,
  "agentCapabilities": {
    "loadSession": true,
    "sessionCapabilities": { "list": {}, "delete": {} },
    "promptCapabilities": { "image": false, "audio": false, "embeddedContext": true }
  },
  "authMethods": [],
  "agentInfo": { "name": "acpw-pool", "version": "<acpw version>" }
}
```

### 3. `session/list`

- 不必带 `_meta.worker`（与 `session/new` 不同）。
- 返回 **公开** id，来自耐久 map ∪ 内存 live 状态。
- 每条：`sessionId`、`cwd`（没有记录则 `""`）、`_meta.worker`、`_meta.live`、`_meta.held`。不发明顶层字段。
- `_meta.worker` 若出现在请求里：只列出该 worker（`acpw stdio NAME` 必须注入，从而只看见自己的 session）。
- 第一版一次返回全部，不设 `nextCursor`。

### 4. `session/delete`

- 参数 `{ "sessionId": "<public>" }`，成功 `{}`。
- 已删除或不存在：**静默成功**。
- 被**另一条**活连接占用：`-32001` `session <id> is held by another client`。本连接占用的可以删。
- 清内存绑定 + 从 `sessions.json` 去掉该键。
- child 若广告 `sessionCapabilities.delete` 则向 child 发 native id 的 `session/delete`；否则只删 mux 映射。
- **不要** SIGTERM 整个 child（一个 child 上可能还有别的 session）。
- 之后 `session/load` / `session/prompt` 对该 id → `-32001` unknown session。

### 5. stdio

[`stdio.py`](../packages/acpw/src/acpw/stdio.py) 在 `session/list` 和 `session/delete` 上也注入 `_meta.worker`（与 `session/new` 一样）。`worker/*` 仍回 `-32601`。不要把 `session/list` 当成 worker 控制面拦掉。

### 6. CLI

风格对齐 `acpw lang`：

- `acpw sessions` — 表：id / worker / cwd / live / held
- `acpw sessions rm ID`
- `acpw sessions prune` — 删所有未被占用的耐久记录；held 的留下

类型放 `packages/acpw/src/acpw/types/`，从 `acpw.types` 导出。`pool.py` 增加 `pool_sessions` / `pool_session_rm` / `pool_sessions_prune`。i18n 字符串写入 `locales.py`。

同步：`skills/acp-workers/SKILL.md` 命令表、`references/pool.md`（「永不回收」改为 list/delete/prune）、`CHANGELOG.md` 的 `未发布`。不 bump 版本。

### 7. 测试

仍用 mock child + `ACPW_CONFIG_DIR` / `ACPW_STATE_DIR` + 随机端口。不碰真 grok。

必须覆盖：

- `initialize` 含 `sessionCapabilities.list` 与 `delete`
- `session/list` 空 / 有 / stdio 按 worker 过滤（两个 worker 时 stdio 只看见自己的）
- `session/delete` 幂等、占用中拒绝、删除后无法 load
- `prune` 不删 held session
- 未知 method 仍 `-32602` `no route:`
- 文档 grep 见上

## 不要做

- 改 RPC 方法名去迁就旧文档
- 自动 TTL
- `_worker/*` 改名
- host 侧 fs/terminal
- ACP v2
- 发版 / bump `0.6.6`
