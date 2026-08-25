# Pool 协议 v2

`acpw daemon`（`run_daemon`）与 `MuxClient` 之间的契约。两边都按本文件实现；**代码是 SSOT**——本文与 [`packages/acpw/src/acpw/daemon.py`](../packages/acpw/src/acpw/daemon.py) 不一致时，改文档。

## 为什么

这是本项目的原生模式：一个常驻 daemon 占一个端口，底下挂若干 stdio children，所以一条 host 连接就能并发驱动多个 agent，并用公开 session id 续上。独立的 `acpw gateway`（一个 worker、一口端口、一把 secret、一条 in-flight 请求）作为 `--no-pool` 保留。

## 端点

```
ws://127.0.0.1:48190/ws?server-key=<secret>
GET /health
```

- Secret 在 `~/.local/state/acp-workers/_pool/secret`，pid 在 `.../pid`，日志在 `.../server.log`，daemon 实际起在哪个 bind 记在 `.../bind`，耐久 session 映射在 `.../sessions.json`。pid 文件可能被并发冷启动的输家覆盖；`/health` 的 `pid` 才是真正在服务的进程。`pool_down` 在 pid 文件不可用时回退到它；`pool_up` 在 health 起来后（含 already）把正确 pid 写回文件。
- Bind 发现顺序：环境变量 `ACPW_POOL_BIND`，然后 `bind` state 文件，最后 `DEFAULT_POOL_BIND`（`0.0.0.0:48190`）。`pool_up()` 写这个文件，其余都读它。
- `/ws` 上 `server-key` 错或缺失 → HTTP 401。
- `GET /health` → `{"ok":true,"kind":"pool","pid":N,"workers":[{"name","kind","alive","pid","sessions"}],"sessions":N}`。两处 session 计数都是 live 绑定，不是耐久记录。
- `/health` 不需要 key。
- 允许多条连接同时存在。

## Daemon 自己应答的消息

在 host 眼里 daemon 就是 ACP agent。Children 在 spawn 时由 daemon 完成 `initialize`；host 看不到 child 的握手。

`initialize` 的 result（`initialize_result()`）：

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

| Method | Result |
| --- | --- |
| `initialize` | 上表。`sessionCapabilities` 广告 `session/list` 与 `session/delete`。 |
| `authenticate` | `{}` |
| `worker/list` | `{"workers":[{"name","kind","alive","pid","sessions"}]}` |
| `worker/up` | params `{"name":str,"cwd":str?}` → `{"name","alive":true,"pid":N,"already":bool,"protocolVersion","agentInfo","agentVersion"}`。Spawn 并跑完 child `initialize`（必要时 `authenticate`）才返回。后三个字段回显 child 自己的握手；没有则为 null。 |
| `worker/down` | params `{"name":str}` → `{"name","stopped":bool}`。杀掉 child 并清掉内存绑定。耐久记录留下，那些 session 仍可按 L2 续。 |
| `session/list` | 见下文。不必带 `_meta.worker`。 |
| `session/delete` | 见下文。 |

## 路由

1. `session/new` 和 `session/load` **必须**带 `params._meta.worker`，值为 registry 里的 worker 名。缺失 → `-32602` `missing _meta.worker`。未知 worker、disabled、kind 不在 allow 列表同属 `-32602`。
2. Daemon 按需 spawn 该 worker 的 child（与 `worker/up` 相同），转发请求，成功时铸造形如 `acpw-s<16 hex>` 的公开 `sessionId`，绑定到 `(worker, child, connection)`。Child 自己的 id 永不到达 host。
3. `session/list`：daemon 自己应答，不转发 child。请求里若有 `_meta.worker`，只列出该 worker（`acpw stdio NAME` 必须注入）。否则列出全部耐久 ∪ 内存 session。
4. `session/delete`：daemon 自己应答。占用规则见下。
5. 其他带 `params.sessionId` 的请求路由到该 session 的 child，必要时先续上。未知或不可续 → `-32001` `unknown session <id>`。Session 当前附着在另一条**未关闭**的连接上 → `-32001` `session <id> is held by another client`。
6. 既不是控制消息、也不绑定 session 的请求 → `-32602` `no route: <method>`。
7. Child 发来、带 `params.sessionId` 的 notification 送到当前附着该 session 的连接。未知或已卸下的丢弃，并记进 daemon 日志。

## Session 耐久

Session 是一段对话，不是一条 socket。三档，按顺序尝试：

| 档 | 状态 | Daemon 做什么 |
| --- | --- | --- |
| L1 | Child 活着，session 在内存 | 重新附着到请求方连接。不经过 agent。 |
| L2 | Child 没了，映射还在 | 再 spawn 该 worker，用 child 原生 id 做 `session/load`，绑回同一个公开 id。 |
| L3 | Daemon 重启过 | 与 L2 相同，映射从 `sessions.json` 读回。 |

- `sessions.json` 映射公开 id → `{"worker":str,"native":str,"cwd":str|null}`。每次绑定都原子写入（临时文件再 rename）。
- L2/L3 要求 child 广告 `agentCapabilities.loadSession`。没有时 `-32001` `worker <name> cannot resume sessions (loadSession not advertised)`。必须在发送 `session/load` **之前**检查。
- 若 `session/load` 返回的 `sessionId` 与送进去的不同，新值成为原生 id。公开 id 永不改变。
- 同一时刻只有一条连接驱动一个 session。占用方不在或其 socket 已关闭时允许附着。

### `session/list`

官方形状。一次返回全部，不设 `nextCursor`。

```json
{
  "sessions": [
    {
      "sessionId": "acpw-s…",
      "cwd": "/path/or/empty",
      "_meta": { "worker": "grok", "live": true, "held": false }
    }
  ]
}
```

- `cwd` 必填。耐久记录没有 cwd 时用 `""`。
- `live`：内存里且 child 仍活。
- `held`：当前有一条未关闭的连接附着。
- 不把 child native id 放进结果。

### `session/delete`

params `{ "sessionId": "<public>" }`，成功 `{}`。

- 已删除或不存在：静默成功。
- 被**另一条**活连接占用：`-32001` `session <id> is held by another client`。本连接占用的可以删。
- 清内存绑定 + 从 `sessions.json` 去掉该键。
- child 若广告 `sessionCapabilities.delete`（或等价的 delete 能力），向 child 转发 native id 的 `session/delete`；否则只删 mux 映射。
- **不** SIGTERM 整个 child。
- 之后对该 id 的 `session/load` / `session/prompt` → `-32001` unknown session。

没有自动 TTL。批量清理走 CLI `acpw sessions prune`（删所有 `held: false` 的耐久记录）。

## 标识符重映射

- **Host → child。** 每个 child 一套整数 JSON-RPC id（`1, 2, 3, …`）。应答时用 host 原来的 id 回给所属连接。
- **Child → host。** Child 发来请求时，daemon 分配形如 `"acpw:<n>"` 的 string id。Host 分配整数，所以 `"acpw:*"` 不会撞车。
- **Session id。** 第三套空间。Daemon 用 `acpw-s<16 hex>` 作为键，双向翻译 `params.sessionId`。
- Response 必须保留 `jsonrpc`、`id`，以及 `result` / `error` 恰好其中一个。

## 并发

- 每个 child 一条 reader 线程排空 stdout，按 id 分发。
- 每个 child 一把写锁；每条连接一把写锁。
- Children 只在**一条长命线程**上 fork（Linux `PR_SET_PDEATHSIG` 绑在父线程上）。
- Child stderr 排到 daemon 日志，带 worker 名前缀，永不进 WebSocket。

## 生命周期

- 连接断开只卸下 session，不结束它们。
- 属于已死连接的 in-flight 请求，答案到达时丢弃。
- Child 退出清掉其 session 的内存绑定。之后走 L2。
- Daemon 收到 SIGTERM 退出并杀掉每个 child。Session 经 L3 回来。

## 错误

| Code | 何时 |
| --- | --- |
| `-32602` | 缺 `_meta.worker`、未知 worker、disabled、kind 不在 allow 列表、无法路由的 method（`no route: …`） |
| `-32001` | 未知 session、被另一客户端占用、或 worker 不能续 |
| `-32000` | 写给 child 失败，或请求做到一半 child 退了 |

## 模块契约

共享常量在 `acpw.paths`：`DEFAULT_POOL_BIND = "0.0.0.0:48190"`，`POOL_STATE_NAME = "_pool"`。响应模型在 `acpw.types`：`PoolWorker`、`PoolStatus`、`PoolStartResponse`、`PoolStopResponse`、`SessionInfo`、`SessionListResponse`、`SessionDeleteResponse`、`SessionPruneResponse`。

`acpw/daemon.py` 暴露：

```python
def run_daemon(bind: str, secret_file: str) -> None: ...   # 阻塞直到 SIGTERM
```

`acpw/pool.py` 暴露：

```python
def pool_secret() -> str: ...
def pool_url(secret: str | None = None) -> str: ...
def pool_live(timeout: float = 1.0) -> bool: ...
def pool_up(bind: str | None = None, workers: list[str] | None = None,
            cwd: str | None = None, timeout: float = 45) -> PoolStartResponse: ...
def pool_down() -> PoolStopResponse: ...
def pool_status() -> PoolStatus: ...
def pool_ping(name: str) -> PingResponse: ...
def pool_run(params: ExecParams) -> ExecResponse: ...
def pool_sessions() -> SessionListResponse: ...
def pool_session_delete(session_id: str) -> SessionDeleteResponse: ...
def pool_sessions_prune() -> SessionPruneResponse: ...
```

`pool_up` 不带 bind 时，解析方式和其余代码相同。health 起来后必须把 `/health` 报告的 pid 写回 pid 文件，already 分支也一样。

`pool_down` 先看 `/health` 的 pid，文件里的 pid 只在 health 不可达时使用。

`pool_ping` 发 `worker/up`，报告 child 的 `agentInfo` 和 `protocolVersion`。

`pool_run`：`params.session_id` 已设时，直接用该 id 发 `session/prompt`。**不要**调 `session/new`，也 **不要** 调 `session/load`。`-32001` 作为失败浮给调用方。

`acpw/client.py`：

```python
class MuxClient:
    def __init__(self, sock: socket.socket) -> None: ...
    def start(self) -> None: ...
    def close(self) -> None: ...
    def rpc(self, method: str, params: dict | None = None, timeout: float = 60.0) -> dict: ...
    def updates(self, session_id: str) -> list[dict]: ...
```

## 客户端义务（`MuxClient`）

- 一条后台 reader 线程；请求经按 host id 索引的 future 返回。
- 用 `{"outcome":{"outcome":"selected","optionId":"allow-once"}}` 应答 `session/request_permission`。
- 用错误 `-32601`（`client fs not offered`）应答 `fs/*` 和 `terminal/*`。
- 按 `sessionId` 收集 `session/update` notification。
- 永远不要在 reader 线程上阻塞用户代码。

标准 ACP 客户端（Zed、acp-devtools、mock-editor）不拨这条 WebSocket。它们拉起 `acpw stdio NAME`：适配层在 `session/new` / `session/load` / `session/list` / `session/delete` 上填 `_meta.worker`，JSON-RPC id 原样过线，不代替 host 应答 permission。`worker/*` 在这一面回 `-32601`。
