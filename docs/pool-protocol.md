# Pool 协议 v2

`acpw daemon`（服务端）与 `MuxClient`（客户端）之间的契约。两边都按本文件实现；代码和本文不一致时，以本文为准报 bug。

## 为什么

这是本项目的原生模式：一个常驻 daemon 占一个端口，底下挂若干 stdio children，所以一条 host 连接就能并发驱动多个 agent，并用公开 session id 续上。独立的 `acpw gateway`（一个 worker、一口端口、一把 secret、一条 in-flight 请求）作为 `--no-pool` 保留。

## 端点

```
ws://127.0.0.1:48190/ws?server-key=<secret>
GET /health
```

- Secret 在 `~/.local/state/acp-workers/_pool/secret`，pid 在 `.../pid`，日志在 `.../server.log`，daemon 实际起在哪个 bind 记在 `.../bind`，耐久 session 映射在 `.../sessions.json`。pid 文件可能被并发冷启动的输家覆盖；`/health` 的 `pid` 才是真正在服务的进程。`pool_down` 在 pid 文件不可用时回退到它；`pool_up` 在 health 起来后（含 already）把正确 pid 写回文件。
- Bind 发现顺序：环境变量 `ACPW_POOL_BIND`，然后 `bind` state 文件，最后 `DEFAULT_POOL_BIND`。`pool_up()` 写这个文件，其余都读它，所以 pool 起在非默认端口时仍能被找到。
- `/ws` 上 `server-key` 错或缺失 → HTTP 401，与每个 worker 的独立 gateway 相同。
- `GET /health` → `{"ok":true,"kind":"pool","pid":N,"workers":[{"name","kind","alive","pid","sessions"}],"sessions":N}`。两处 session 计数都是 live 绑定，不是耐久记录，所以 child 死后会掉到零，尽管那些 session 仍可续。
- `/health` 不需要 key。因此一份对着**另一份** state 目录起的 daemon，看起来仍 live，直到 `/ws` 回 401；客户端应把这一点说清楚，而不是报 pool 已停。
- 允许多条连接同时存在。没有 `conn_lock`。

## Daemon 自己应答的消息

在 host 眼里 daemon 就是 ACP agent。Children 在 spawn 时由 daemon 完成 initialize；host 看不到 child 的 `initialize`。

| Method | Result |
| --- | --- |
| `initialize` | `{"protocolVersion":1,"agentCapabilities":{"loadSession":true,"promptCapabilities":{"image":false,"audio":false,"embeddedContext":true}},"authMethods":[],"agentInfo":{"name":"acpw-pool","version":"<acpw version>"}}` |
| `authenticate` | `{}` |
| `worker/list` | `{"workers":[{"name","kind","alive","pid","sessions"}]}` |
| `worker/up` | params `{"name":str,"cwd":str?}` → `{"name","alive":true,"pid":N,"already":bool,"protocolVersion","agentInfo","agentVersion"}`。Spawn 该 child 并跑完 `initialize`（child 声明了 auth methods 时再加上 `authenticate`）才返回。后三个字段回显 child 自己的握手，调用方才能知道打到了哪个 agent，而不是只听到 daemon；child 没带这些字段时为 null。 |
| `worker/down` | params `{"name":str}` → `{"name","stopped":bool}`。杀掉 child 并清掉内存绑定。耐久记录留下，那些 session 仍可按 L2 续。 |

## 路由

1. `session/new` 和 `session/load` **必须**带 `params._meta.worker`，值为 registry 里的 worker 名。缺失或未知 → 错误 `-32602`，message 为 `missing _meta.worker` / `unknown worker <name>`。worker 在 registry 里 `enabled: false` → `-32602`，`worker <name> is disabled in registry`。kind 不在本机 allow 列表 → `-32602`，`kind <kind> is not allowed`。
2. Daemon 按需 spawn 该 worker 的 child（与 `worker/up` 相同），转发请求，成功时铸造形如 `acpw-s<16 hex>` 的公开 `sessionId`，绑定到 `(worker, child, connection)`。Child 自己的 id 永不到达 host。这个 id 是随机的，不是序号：session 活过它的连接，知道这个 id 就是续对话的能力。
3. 其他带 `params.sessionId` 的请求路由到该 session 的 child，必要时先续上（见 Session 耐久）。未知 session 或不可续 → 错误 `-32001`，message 为 `unknown session <id>`。Session 当前附着在另一条**未关闭**的连接上 → 错误 `-32001`，message 为 `session <id> is held by another client`。
4. 既不是控制消息、也不绑定 session 的请求 → 错误 `-32602`，message 为 `no route: <method>`。
5. Child 发来、带 `params.sessionId` 的 notification 送到当前附着该 session 的连接。未知或已卸下的 session 的 notification 丢弃，并记进 daemon 日志。

## Session 耐久

Session 是一段对话，不是一条 socket。它活过打开它的那条连接，再次出示 id 即可续。三档，按顺序尝试：

| 档 | 状态 | Daemon 做什么 |
| --- | --- | --- |
| L1 | Child 活着，session 在内存 | 重新附着到请求方连接。不经过 agent。 |
| L2 | Child 没了，映射还在 | 再 spawn 该 worker，用 child 原生 id 做 `session/load`，绑回同一个公开 id。 |
| L3 | Daemon 重启过 | 与 L2 相同，映射从 `sessions.json` 读回。 |

- `sessions.json` 映射公开 id → `{"worker":str,"native":str,"cwd":str|null}`。每次绑定都原子写入（临时文件再 rename）。记录故意活过 child：这正是 L2 和 L3 能工作的原因。
- L2 和 L3 要求 child 广告 `agentCapabilities.loadSession`。没有时续失败，错误 `-32001`，message 为 `worker <name> cannot resume sessions (loadSession not advertised)`。Daemon 必须在发送 `session/load` **之前**检查 spawn 时缓存的能力，这样不能续的 agent 会明确说出来，而不是回一个不透明错误。
- 若 `session/load` 返回的 `sessionId` 与送进去的不同，新值成为该 session 的原生 id，并改写记录。公开 id 永不改变。
- 同一时刻只有一条连接驱动一个 session。占用方不在或其 socket 已关闭时允许附着；从活着的占用方手里抢是不允许的。
- Session 随 worker 一起「死」只体现在 L1 不再适用。`worker/down` 和 child 退出会清掉内存绑定，但留下耐久记录。

## 标识符重映射

两套独立的 id 空间在 daemon 相遇。绝不把一套泄漏到另一套。

- **Host → child。** Daemon 为每个 child 分配一套新的整数 id（`1, 2, 3, …`，计数器按 child 分开），并记住 `child.pending[child_id] = handler`。Child 用该 id 应答时，daemon 用 host **原来的** id 原样回给所属连接（可能是 int 也可能是 string）。
- **Child → host。** Child 发来请求（`session/request_permission`、`fs/read_text_file`、`fs/write_text_file`、`terminal/*`）时，daemon 从全局计数器分配形如 `"acpw:<n>"` 的 **string** id，存 `conn.inbound[acpw_id] = (child, child_side_id)`，并转发给拥有该 session 的连接。Host 应答 `"acpw:<n>"` 时，daemon 用 child 原来的 id 写回 child。
  用 string id 是故意的：host 分配整数，所以 `"acpw:*"` 永远不会和 host 选的 id 撞车。
- **Session id。** 第三套空间，存在的原因：children 自己选 session id，两个 child 很可能选出同一字符串，若用 child 的 id 做扁平表键，后续请求会静默打到错误的 agent。Daemon 用 `acpw-s<16 hex>` 作为 session 键，并双向翻译 `params.sessionId`：上行时 child id → 公开 id（`session/new` 和 `session/load` 的结果、child 的 notification 和 request），下行时公开 id → child id。Child 重启会拿到新的 generation token，回收的 id 不能继承已死 session。
- Response 必须保留 `jsonrpc`、`id`，以及 `result` / `error` 恰好其中一个。

## 并发

- 每个 child 有一条 reader 线程永远排空 stdout，按 id 分发；任何地方都没有「读到我的 id 为止」。
- 每个 child 一把写锁；每条连接一把写锁。一帧 WebSocket 和一行 stdio 各自原子写出。
- 每个 child 可以有多条 in-flight 请求。背后的 agent 是否真并行，是 agent 自己的事；daemon 不为它串行化。
- Children 只在**一条长命线程**上 fork。Linux 把 `PR_SET_PDEATHSIG` 绑在父*线程*而不是父进程上：设了它的 agent（Grok 会设）在 fork 它的那条线程退出的瞬间就收到 SIGTERM。Daemon 每条请求跑在临时线程上，所以在请求线程里 fork，会让 child 在自己的 `session/new` 刚交接出去就被内核杀掉——rc=143，且 daemon 从未调用过 kill。
- Child stderr 排到 daemon 日志，带 worker 名前缀，永不进 WebSocket。裸行无法归属到某个 worker。

## 生命周期

- 连接断开只是**卸下**它的 session，并不结束它们。Children 保持预热，耐久记录留在磁盘。
- 属于已死连接的 in-flight 请求，答案到达时丢弃。
- Child 退出会清掉其 session 的内存绑定。之后针对其中之一的请求走 L2。
- Daemon 收到 SIGTERM 退出并杀掉每个 child。Session 经 L3 回来。

## 错误

| Code | 何时 |
| --- | --- |
| `-32602` | 缺 `_meta.worker`、未知 worker、disabled、kind 不在 allow 列表、无法路由的 method |
| `-32001` | 未知 session、被另一客户端占用、或 worker 不能续 |
| `-32000` | 写给 child 失败，或请求做到一半 child 退了 |

## 模块契约

共享常量已在 `acpw.paths`：`DEFAULT_POOL_BIND = "0.0.0.0:48190"` 和 `POOL_STATE_NAME = "_pool"`。响应模型已在 `acpw.types`：`PoolWorker`、`PoolStatus`、`PoolStartResponse`、`PoolStopResponse`。

`acpw/daemon.py` 恰好暴露：

```python
def run_daemon(bind: str, secret_file: str) -> None: ...   # 阻塞直到 SIGTERM
```

`acpw/pool.py` 恰好暴露：

```python
def pool_secret() -> str: ...                    # 读取或创建 pool secret
def pool_url(secret: str | None = None) -> str: ...
def pool_live(timeout: float = 1.0) -> bool: ...  # GET /health
def pool_up(bind: str | None = None, workers: list[str] | None = None,
            cwd: str | None = None, timeout: float = 45) -> PoolStartResponse: ...
def pool_down() -> PoolStopResponse: ...
def pool_status() -> PoolStatus: ...
def pool_ping(name: str) -> PingResponse: ...
def pool_run(params: ExecParams) -> ExecResponse: ...
```

`pool_up` 不带 bind 时，解析方式和其余代码相同；把 daemon 起在其余代码不会去看的地址，只会得到一个谁都找不到的 pool。health 起来后必须把 `/health` 报告的 pid 写回 pid 文件，already 分支也一样——并发冷启动的输家可能已经把文件写成一个已死的 pid，或不写。

`pool_down` 先看 `/health` 的 pid，文件里的 pid 只在 health 不可达时使用。只信文件的话，文件一旦被覆盖或丢失，daemon 就关不掉。

`pool_ping` 必须碰到指定的 worker，而不是挡在前面的 daemon：发 `worker/up`，报告 child 的 `agentInfo` 和 `protocolVersion`。只和 pool 握手证明不了调用方要的那个 agent，还会把坏掉的 agent 二进制报成健康。

`pool_run` 续会话规则：`params.session_id` 已设时，直接用该 id 发 `session/prompt`。**不要**调 `session/new`，也 **不要** 调 `session/load` —— 续是 daemon 的职责。`-32001` 作为失败浮给调用方；默默开一个新 session 会在谁都不知道的情况下丢掉对话。

`acpw/client.py` 在不碰 `AcpClient` 的前提下增加：

```python
class MuxClient:
    def __init__(self, sock: socket.socket) -> None: ...
    def start(self) -> None: ...                  # 拉起 reader 线程
    def close(self) -> None: ...
    def rpc(self, method: str, params: dict | None = None, timeout: float = 60.0) -> dict: ...
    def updates(self, session_id: str) -> list[dict]: ...   # 目前看到的 session/update params
```

## 客户端义务（`MuxClient`）

- 一条后台 reader 线程；请求经按 host id 索引的 future 返回。
- 用 `{"outcome":{"outcome":"selected","optionId":"allow-once"}}` 应答 `session/request_permission`。
- 用错误 `-32601`（`client fs not offered`）应答 `fs/*` 和 `terminal/*`，与今天的 `AcpClient` 一致。
- 按 `sessionId` 收集 `session/update` notification。
- 永远不要在 reader 线程上阻塞用户代码。

标准 ACP 客户端（Zed、acp-devtools、`mock-editor`）不拨这条 WebSocket。它们拉起 `acpw stdio NAME`：适配层在 `session/new` / `session/load` 上填 `_meta.worker`，JSON-RPC id 原样过线，不代替 host 应答 permission。daemon 路由不变。
