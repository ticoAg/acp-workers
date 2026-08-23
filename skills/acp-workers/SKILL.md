---
name: acp-workers
description: "通过一条常驻 WebSocket 把编码任务派给多个 agent 进程（grok/claude/codex/cursor）。用 --session-id 续会话。Host 规划、限定范围并验收；worker 只执行。USE FOR: acpw up/run/down, --session-id, 48190, 一个 WebSocket 多个 agent, 并发派发, grok agent stdio, ACP websocket, 常驻 ACP. DO NOT USE FOR: grok TUI consult/debate (grok-build-connector); MCP servers; grok -p; grok agent stdio in a tty; treating worker output as verified."
license: MIT
compatibility: "需要 Python 3.12+ 和 uv。CLI 名为 acpw。"
metadata:
  author: ticoAg
  version: "0.6.4"
---

# ACP Workers

Host 只做规划、派发、验收。执行面是**一个**常驻 WebSocket（`48190`，一把 secret），底下挂多个 agent 进程。所有操作走 `acpw`。默认输出 markdown；要整份字段加 `--json`，或 `acpw output set json` 持久化。

`acpw up` 起这个 socket；`acpw run NAME` 在上面开或续一段会话，返回 `session_id`；下次带 `--session-id` 就能续。`acpw run` 在 socket 还没起时会自己起一份。独立 gateway / `grok agent serve` 只在 `--no-pool` 时出现。见 [references/pool.md](references/pool.md)。

## 何时使用

- 把一件可验收的编码任务派给 grok / claude / codex / cursor
- 一条 WebSocket 同时驱动多个 agent
- 用上次返回的 `session_id` 把对话续上

## 何时不用

- 只想和 grok 对话或多方辩论 → `grok-build-connector`
- 配置 MCP server、跑 `grok -p`、在 tty 里手动 `grok agent stdio`
- 把 worker 的自我报告当成验收结论

## 前置条件

```bash
bash scripts/ensure-acpw.sh
```

幂等，且带版本闸门：已装且版本够就报 `already`，没装或低于脚本里的 `required_version` 就装/升到位并报 `installed` / `updated`。装完自动跑 `acpw selfcheck`，结果落在 `selfcheck` 字段（`pass` / `fail` / `skipped`）。想主动追最新版加 `--update`，跳过自检加 `--no-selfcheck`。

`"ok":false` 时按 `notes` 处理，不要自己另想装法：缺 uv、`~/.local/bin` 不在 PATH，或自检没过（完整报告在 stderr）。补全要单独加 `--completion`（会写 `~/.bashrc`）。细节见 [references/install.md](references/install.md)。

## 角色

| 词 | 含义 |
| --- | --- |
| Host | 当前主 agent。拆任务、选 worker、自己跑测试 |
| Socket | `ws://127.0.0.1:48190/ws?server-key=SECRET`，本项目的原生入口 |
| Worker | 这个 socket 底下的一个 stdio 子进程（grok / claude / codex / cursor） |
| Session | 一段对话。公开 id 长 `acpw-s` + 16 位 hex，跨连接、跨 child、跨 daemon 重启可续 |

默认监听 `0.0.0.0:48190`，连接拨 `127.0.0.1`。child 是 always-approve 且 secret 明文过线，别把端口放到不可信网络——`acpw selfcheck` 会就此告警。`--no-pool` 才用独立端口：grok `48191`，claude `48192`，codex `48193`，cursor `48194`。

## 工作流

### 步骤 1：探活

```bash
acpw doctor && acpw ls
```

`ls` 里 `## pool` 的 `live: true` 和 workers 表的 `via` 为 `pool` 才是原生路径。每个 worker 自己的端口空着是正常的。

### 步骤 2：起 socket

```bash
acpw up                              # 只起 WebSocket
acpw up grok claude --cwd "$PWD"     # 顺带预热这些 child
```

### 步骤 3：写 prompt

一次只派一件可验收的事，写清楚改哪些文件、完成标准是什么。长 prompt 落到文件走 `-f`，别塞进命令行。

### 步骤 4：派发

```bash
acpw run grok -f /tmp/a.txt
acpw run claude -f /tmp/b.txt &
acpw run grok -f /tmp/c.txt --session-id acpw-s<上次返回的 id>
```

第一次 `run` 返回的 `session_id` 留下来。连接断了、child 死了、daemon 重启了，把这个 id 再贴回去就能续。对话历史回不回得来，取决于那个 agent 是否广告并执行 `session/load`。第二个 grok 进程：`acpw add grok-b --kind grok`。默认超时 600s。

### 步骤 5：验收

`ok` 只代表 ACP 回合正常结束，不代表任务做对。Host 必须自己看 diff、跑测试。`stop_reason` 为 `cancelled` 一律当失败处理。

## 命令

| 命令 | 作用 |
| --- | --- |
| `version` | 打印已装版本、Python、包路径（也可 `acpw --version`） |
| `selfcheck` | 九项自检 + mock 往返；有 `fail` 则退出 1（`--no-live` 只查静态项） |
| `ls` | 配置 + 探活；含 `pool` 字段（别名 `status`） |
| `doctor` | 检查适配器二进制是否在 PATH |
| `up` / `down` | 起停那一个 WebSocket；`up grok claude` 预热 child，`down grok` 只停一个 child（别名 `start` / `stop`） |
| `ping` / `run` | 握手 / 派活（`-p` 或 `-f`）。`run` 返回 `session_id`；续会话加 `--session-id` |
| `pool up` / `pool down` / `pool ls` | 与 `up` / `down` / `ls` 的 pool 字段同义，留给脚本 |
| `add` / `rm` | 登记、注销 URL |
| `lang` | `acpw lang set zh-CN` 写入配置；`acpw lang` / `lang get` 查看。一次调用用 `--lang` |
| `output` | 默认 markdown。`acpw output set json` 写入配置；一次调用用 `--json` 或 `--format` |
| `install` / `uninstall` | bash 补全；`--purge` 再停 worker 并删 registry/state |

## 验收清单

- [ ] `acpw selfcheck` 的 `failed` 为空（装完自动跑过一次）
- [ ] `acpw ls` 的 `## pool` 里 `live: true`，或 `run` 自己拉起过 socket
- [ ] 续会话时用的是上次输出里的 `session_id`
- [ ] `acpw run` 返回的 `stop_reason` 不是 `cancelled`
- [ ] Host 自己看过 diff
- [ ] Host 自己跑过测试并贴出真实结果

## 常见坑

| 问题 | 做法 |
| --- | --- |
| 空跑 `grok agent stdio` / `grok agent serve` | 用 `acpw up grok` 或直接 `acpw run grok` |
| 把 worker 回复当作修好了 | 自己跑测试 |
| 密钥进聊天记录 | 只读 `acpw ls`；secret 在 `~/.local/state/acp-workers/` |
| 一个 prompt 塞多件事 | 拆开，逐件派发逐件验收 |
| 把 pool 当启动加速 | 子进程本来就常驻；换来的是一个入口和并发，不是少等进程 |
| `--session-id` 续上了但对话是空的 | daemon 能重建 session；历史回不回得来看 agent 是否广告并执行 `session/load`。没广告会报 `worker <name> cannot resume sessions (loadSession not advertised)` |
| `session <id> is held by another client` | 同一时刻一条连接占用一个 session；等那条连接断开后再续 |
| 批量派发久了变慢 | 每次不带 `--session-id` 的 `run` 都新开一个 session，且**永不回收**。要么复用 `--session-id`，要么 `acpw down` 后删 `_pool/sessions.json` |
| daemon 挂了名下 child 一起停 | session 映射留在 `_pool/sessions.json`，daemon 再起后可续。要隔离进程就 `acpw up NAME` 加 `--no-pool` |

## 参考

- [scripts/ensure-acpw.sh](scripts/ensure-acpw.sh) — 幂等装好 CLI，输出一行 JSON
- [references/install.md](references/install.md) — 安装、补全、卸载顺序
- [references/protocol.md](references/protocol.md) — WebSocket URL、ACP 握手序列、stdio 桥、Grok 继承什么
- [references/pool.md](references/pool.md) — 默认走 pool、三档 session、所有权、错误码、与独立 gateway 怎么选
- [assets/registry.example.json](assets/registry.example.json) — registry 结构示例
