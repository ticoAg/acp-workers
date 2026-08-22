# Pool

本项目的原生入口是**一条** WebSocket：`acpw up` 起的那个 daemon，监听 `0.0.0.0:48190`，一把 secret。底下同时挂着若干 stdio 子进程（grok / claude / codex / cursor / mock）。Host 拨 `127.0.0.1`，就可以并发驱动多个 agent，并用 `--session-id` 把对话续上。

```bash
acpw up                              # 只起 WebSocket
acpw up grok claude --cwd "$PWD"     # 顺带预热这些 child
acpw run grok -f /tmp/a.txt          # 返回 session_id
acpw run claude -f /tmp/b.txt &
acpw run grok -f /tmp/c.txt --session-id acpw-s…
acpw down grok                       # 只停一个 child；daemon 还在
acpw down                            # 停这条 WebSocket
```

`acpw run` / `acpw ping` 在 socket 还没起时会自己起一份。判定看的是 `stdio_argv`，不是 transport 种类——grok 仍然是 `native_ws`（`--no-pool` 才起 `serve`），但 adapter 同时带了 `grok agent --always-approve --no-leader stdio`，所以 pool 也能拉它。`--no-pool` 改走该 worker 自己的 gateway / serve；`--pool` 强制走这条 socket。显式 `--url` 绕开 pool，因为它指名某个 socket。

它**不**省启动时间。以前每个 stdio worker 各自占一口端口一把密钥，一次只接一个 WebSocket、一次只做一条 in-flight 请求。现在这些 child 收进同一个进程。换来的是一个入口、一把密钥、一条连接上的并发派发，以及下面三档 session 耐久，不是少等进程起来。

独立 gateway / serve 还在，是逃生口。一个 registry 名对应 pool 里**一个** child；要两个 grok 进程就再登记一个同 kind：`acpw add grok-b --kind grok`。`--no-pool` 的 grok 仍是 `grok agent serve`（`48191`）。

## 何时用

| 用这条 WebSocket（默认） | 用独立 gateway / serve（`--no-pool`） |
| --- | --- |
| 一条长连接上同时跟几个 agent 说话 | 要隔离故障面：一个挂了别的还在 |
| 只想记 `48190` 和一把 secret | 要按端口、按 `<name>/server.log` 追查 |
| 多个 `acpw run` 同时打过来，并用 `--session-id` 续 | 调试单个独立 gateway / serve |

这条 socket 是单点故障：daemon 一挂，名下 child 全停。公开 session 映射写在 `_pool/sessions.json`，daemon 再起后同一 `--session-id` 仍可续。要隔离进程就 `acpw up NAME --no-pool`。

## 入口

```
ws://127.0.0.1:48190/ws?server-key=<secret>
GET /health
```

| 路径 | 内容 |
| --- | --- |
| `~/.local/state/acp-workers/_pool/secret` | 这一把 secret |
| `.../_pool/pid` | daemon pid |
| `.../_pool/server.log` | daemon 日志；child stderr 也进这里，不进 WebSocket |
| `.../_pool/bind` | daemon 实际起在哪个 bind。`acpw up` 不写 `--bind` 时：先 `ACPW_POOL_BIND`，再这个文件，最后才是 `0.0.0.0:48190` |
| `.../_pool/sessions.json` | 公开 session id → `{worker, native, cwd}`；原子写。`acpw down` 再起后靠它续 L3 |

错或没带 `server-key` → HTTP `401`，和独立 gateway 一样。`GET /health` 不需要 key，回 `kind` 为 `pool` 的 JSON。因此一份对着**别的** state 目录起的 daemon，`/health` 仍显示 live，鉴权才 401——CLI 这时会点出 bind、secret 路径，以及 `acpw down` 或把 `ACPW_STATE_DIR` 指到那一份。监听面是 `0.0.0.0`，也就是说这一把 secret 明文过线且 child 是 always-approve——别把 `48190` 放到不可信网络，`acpw selfcheck` 的 `exposure` 项会提醒。State 目录仍吃 `ACPW_STATE_DIR`，见 [install.md](install.md)。独立握手见 [protocol.md](protocol.md)。

## 命令

| 命令 | 作用 |
| --- | --- |
| `acpw up` | 起这条 WebSocket；已 live 返回 `already`。可带若干 NAME 预热 child |
| `acpw down` | 停这条 WebSocket，并杀掉名下每个 child |
| `acpw down NAME` | 只停一个 child；daemon 和 `sessions.json` 留下 |
| `acpw ls` | 探活；含 `pool` 字段，worker 的 `via` 是 `pool` 或 `gateway` |
| `acpw run NAME --session-id <id>` | 续上次返回的那段对话 |
| `acpw run NAME --no-pool` | 强制走该 worker 自己的 gateway / serve |
| `acpw ping NAME` | spawn/initialize 目标 child，回报它的 `agentInfo` / `protocolVersion`，不是 daemon 自己的身份 |
| `acpw pool up` / `down` / `ls` | 与上面同义，留给脚本；`up` 可写 `--bind` |

`acpw run NAME` / `acpw ping NAME` 默认：NAME 有 stdio 命令就走这条 socket，daemon 不在就先起；否则走原来的独立端口。`--url` 指名道姓某个 socket，绕开 pool。`acpw up` 起的是空 daemon，某个 worker 第一次 `session/new` 才 spawn 对应 child。

```bash
acpw up
acpw run claude -f /tmp/task.txt
acpw ping cursor
acpw run grok -f /tmp/task.txt --session-id acpw-s…
acpw add grok-b --kind grok
acpw run grok-b -f /tmp/other.txt
acpw run grok -f /tmp/task.txt --no-pool         # 独立 serve，48191
acpw down grok
acpw down
```

## Session 三档

公开 id 长 `acpw-s` 加 16 位 hex，故意不可猜。它比开它的那条连接活得长：

| 档 | 活过什么 | 怎么续 |
| --- | --- | --- |
| L1 | 创建它的那条 WebSocket | 两次独立的 `acpw run --session-id <id>` 接到同一段对话 |
| L2 | agent 子进程 | child 死了 daemon 会再 spawn，并重放 `session/load` |
| L3 | daemon 自己 | 映射落在 `_pool/sessions.json`；`acpw down` 再起后同一 id 仍可用 |

耐久指的是 daemon **能把 session 再挂上**。对话历史回不回得来，取决于 agent 是否广告并执行 `session/load`。调用 `session/load` 之前 daemon 会看 child 的 `agentCapabilities.loadSession`；没有或为 false 就返回 `worker <name> cannot resume sessions (loadSession not advertised)`，不会默默开一个空白 session。

同一时刻一个 session 只给一条连接。另一条活连接正占着时，续会返回 `session <id> is held by another client`。那条连接断开后 session 卸下，可以再续。

Session 只增不减：`sessions.json` 里的记录故意活过 child 和 daemon（L2、L3 正靠它），daemon 里没有回收、过期或数量上限。批量派任务时每个不带 `--session-id` 的 `acpw run` 都会新开一段对话，长期跑要么复用 id，要么 `acpw down` 后删掉 `_pool/sessions.json`。

## 路由

Host 眼里 daemon 就是 ACP agent。Child 的 `initialize` 在 spawn 时由 daemon 做完，host 看不到。

| 请求 | 怎么走 |
| --- | --- |
| `session/new` | `params._meta.worker` 必须是 registry 里的 `name`，用来选定 agent |
| 之后所有带 `params.sessionId` 的请求 | 跟到该 session 绑定的 child；必要时走 L2/L3 续上 |
| 连接断开 | 占用解除，session 仍在（L1）；child 仍常驻 |

Pool 发给你的 `sessionId` 是 daemon 自己的公开 id，不是 child 内部那个——child 之间的 id 会撞，daemon 负责两边翻译。

`acpw run NAME` 把 NAME 填进 `_meta.worker`。换 agent 就再 `session/new` 一次。CLI 每次调用开一条新连接；把上次返回的 `--session-id` 再贴上去即可续。

## 错误码

| 码 | 含义 | 做法 |
| --- | --- | --- |
| `-32602` | 缺 `_meta.worker`、未知 worker、或这条 method 无法路由 | 确认 `session/new` 带了 [registry](../assets/registry.example.json) 里的 `name`；其它 method 必须带已经拿到的 `sessionId` |
| `-32001` | 未知 session；被另一条活连接占用（`session <id> is held by another client`）；或 child 不能续（`worker <name> cannot resume sessions (loadSession not advertised)`） | 核对 id；等占用方断开；不要对没广告 `loadSession` 的 worker 续 |
| `-32000` | 写给 child 失败，或请求做到一半 child 退了 | 看 `_pool/server.log`，`acpw ls` 看 `pool` 和 `via`，必要则 `acpw down` / `acpw up` |

## 排障

| 问题 | 做法 |
| --- | --- |
| `acpw ls` 的 `pool.live` 为假 | `acpw run` / `acpw ping` 会自己起 daemon；要预热就 `acpw up NAME`。读 `_pool/server.log` |
| HTTP `401` | URL 带 `server-key`，值来自 `_pool/secret`。若 `/health` 是 live 却 401：daemon 是对着另一份 state 起的，按 CLI 提示 `acpw down` 或改 `ACPW_STATE_DIR` |
| `-32602` `unknown worker` | 先 `acpw ls` / `acpw add`；`_meta.worker` 用登记名 |
| `-32001` 未知 session | id 不在 `sessions.json` / 内存里；重新 `session/new` |
| `-32001` held by another client | 等那条连接断开后再续 |
| `-32001` cannot resume sessions | 该 worker 没广告 `loadSession`；续不了，别指望空白 session 顶上 |
| `ping` 看起来通、agent 其实坏了 | `ping` 会碰到 child；仍不通就看 `_pool/server.log` |
| 一个 child 把整个 pool 拖死 | 预期。改 `acpw up NAME --no-pool` |
| 同一 NAME 既 `--no-pool` 又进了 pool | 两份进程，session 不能混用；`run` 用 `--pool` / `--no-pool` 选边 |
