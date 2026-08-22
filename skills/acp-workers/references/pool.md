# Pool

Pool 是监听 `0.0.0.0:48190` 的一个常驻 daemon：一把 secret，底下同时挂着若干 stdio 子进程。Host 只连这一条 WebSocket（拨 `127.0.0.1`），就可以并发驱动多个 agent。

它**不**省启动时间。Claude / Codex / Cursor 的 stdio 子进程以前就由 `acpw gateway` 常驻着——一 worker 一口端口一把密钥，而且一次只接一个 WebSocket、一次只做一条 in-flight 请求。Pool 把这些 child 收进同一个进程。换来的是一个入口、一把密钥、一条连接上的并发派发，以及**这条连接上**的 session 复用，不是少等进程起来。

独立 gateway 还在。Grok 仍是 `grok agent serve`（`48191`），不走 stdio 桥。

## 何时用

| 用 pool | 用独立 gateway / serve |
| --- | --- |
| 一条长连接上同时跟几个 agent 说话 | 要隔离 blast radius：一个挂了别的还在 |
| 只想记 `48190` 和一把 secret | 要按端口、按 `<name>/server.log` 追查 |
| 多个 `acpw run` 同时打过来 | 派 grok（native serve，本来就不进 pool），或调试单个 worker |

Pool 是单点故障：daemon 一挂，名下 child 全停。今天 grok `48191`、claude `48192`、codex `48193`、cursor `48194` 各是各的进程。要隔离就 `acpw up NAME`，`run` 加 `--no-pool`。

## 入口

```
ws://127.0.0.1:48190/ws?server-key=<secret>
GET /health
```

| 路径 | 内容 |
| --- | --- |
| `~/.local/state/acp-workers/_pool/secret` | pool 这一把 secret |
| `.../_pool/pid` | daemon pid |
| `.../_pool/server.log` | daemon 日志；child stderr 也进这里，不进 WebSocket |
| `.../_pool/bind` | daemon 实际起在哪个 bind；`pool up` 写，其它命令读 |

错或没带 `server-key` → HTTP `401`，和 per-worker gateway 一样。`GET /health` 回 `kind` 为 `pool` 的 JSON。监听面是 `0.0.0.0`，也就是说这一把 secret 明文过线且 child 是 always-approve——别把 `48190` 放到不可信网络，`acpw selfcheck` 的 `exposure` 项会提醒。State 目录仍吃 `ACPW_STATE_DIR`，见 [install.md](install.md)。Per-worker 握手见 [protocol.md](protocol.md)。

## 命令

| 命令 | 作用 |
| --- | --- |
| `acpw pool up` | 后台起 daemon；已 live 返回 `already` |
| `acpw pool ls` | 探活、child、session 计数（别名 `status`） |
| `acpw pool down` | 停 daemon，并杀掉它名下每个 child |
| `acpw run NAME --pool` | 强制走 pool |
| `acpw run NAME --no-pool` | 强制走该 worker 自己的 gateway / serve |

`acpw run NAME` 默认：daemon live 且 NAME 是 stdio worker 才走 pool，否则走原来的 per-worker 端口。grok 是 native serve，不在 pool 的管辖内——不写 `--no-pool` 也不会被路由进去，写了 `--pool` 才会（然后失败）。`--url` 指名道姓某个 socket，同样绕开 pool。`pool up` 起的是空 daemon，某个 worker 第一次 `session/new` 才 spawn 对应 child；`--worker NAME` 可重复，用来预热。

```bash
acpw pool up --worker claude --worker cursor
acpw pool ls
acpw run claude -f /tmp/task.txt                 # daemon live → 走 pool
acpw run cursor -f /tmp/other.txt --pool
acpw run grok -f /tmp/task.txt                   # grok 仍走 48191，无需 --no-pool
acpw pool down
```

## 路由

Host 眼里 daemon 就是 ACP agent。Child 的 `initialize` 在 spawn 时由 daemon 做完，host 看不到。

| 请求 | 怎么走 |
| --- | --- |
| `session/new` | `params._meta.worker` 必须是 registry 里的 `name`，用来选定 agent |
| 之后所有带 `params.sessionId` 的请求 | 跟到该 session 绑定的 child |
| 连接断开 | 这条连接上的 session 绑定作废；child 仍常驻 |

Pool 发给你的 `sessionId` 长 `acpw-s1` 这样，是 daemon 自己的编号，不是 child 内部那个——child 之间的 id 会撞，daemon 负责两边翻译。session 只认开它的那条连接，别的连接拿着 id 也用不了（`-32001`）。

`acpw run NAME` 把 NAME 填进 `_meta.worker`。换 agent 就再 `session/new` 一次。CLI 每次调用开一条新连接，所以 pool 上 `--session-id` 跨两次 `acpw run` 续不上；要续会话走独立 gateway 加 `--no-pool`。

## 错误码

| 码 | 含义 | 做法 |
| --- | --- | --- |
| `-32602` | 缺 `_meta.worker`、未知 worker、或这条 method 无法路由 | 确认 `session/new` 带了 [registry](../assets/registry.example.json) 里的 `name`；其它 method 必须带已经拿到的 `sessionId` |
| `-32001` | session 未知或已死（连接断了、child 退了） | 重新 `session/new`；不要对 pool 跨进程 `--session-id` |
| `-32000` | 写给 child 失败，或请求做到一半 child 退了 | 看 `_pool/server.log`，`acpw pool ls` 看 `alive`，必要则 `pool down` / `pool up` |

## 排障

| 问题 | 做法 |
| --- | --- |
| `acpw pool ls` 不 live | `acpw pool up`；读 `_pool/server.log` |
| HTTP `401` | URL 带 `server-key`，值来自 `_pool/secret` |
| `-32602` `unknown worker` | 先 `acpw ls` / `acpw add`；`_meta.worker` 用登记名 |
| `-32001` | 连接已断或 child 已死；重新 `session/new` |
| 一个 child 把整个 pool 拖死 | 预期。改 `acpw up NAME` 独立端口 |
| 同一 NAME 既 `up` 又进了 pool | 两份进程，session 不能混用；`run` 用 `--pool` / `--no-pool` 选边 |
