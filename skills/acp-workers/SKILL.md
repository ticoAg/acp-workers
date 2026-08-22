---
name: acp-workers
description: "Dispatch coding work to resident ACP workers over loopback WebSocket via the acpw CLI (Grok native serve; Claude/Codex/Cursor stdio bridged). Host agent plans, scopes, and verifies; workers execute. USE FOR: acpw ls/up/run, acpw pool, --pool/--no-pool, 48190, 并发派发, grok agent serve, ACP websocket, 常驻 ACP, 派发给 grok/claude/codex/cursor, 服务发现. DO NOT USE FOR: grok TUI consult/debate (grok-build-connector); MCP servers; grok -p; grok agent stdio in a tty; treating worker output as verified."
license: MIT
compatibility: "Requires Python 3.12+ and uv. CLI name is acpw."
metadata:
  author: ticoAg
  version: "0.3.0"
---

# ACP Workers

Host agent 只做规划、派发、验收；执行面是本机常驻的 ACP WebSocket worker。所有操作走 `acpw`，每条命令输出一行 JSON。

stdio worker 也可以收进同一个 pool daemon（端口 `48190`，一把 secret）；独立 gateway 仍在。见 [references/pool.md](references/pool.md)。

## When to Use

- 把一件可验收的编码任务派给 grok / claude / codex / cursor 后台执行
- 查看、启动、停止常驻 worker（`acpw ls` / `up` / `down`）
- 复用别处已经起好的 `grok agent serve`，登记成 worker
- 一条连接并发派给多个 stdio worker，或只想记一个端口一把密钥 → `acpw pool`

## When Not to Use

- 只想和 grok 对话或多方辩论 → `grok-build-connector`
- 配置 MCP server、跑 `grok -p`、在 tty 里手动 `grok agent stdio`
- 把 worker 的自我报告当成验收结论

## Prerequisites

```bash
bash scripts/ensure-acpw.sh
```

幂等，且带版本闸门：已装且版本够就报 `already`，没装或低于脚本里的 `required_version` 就装/升到位并报 `installed` / `updated`。装完自动跑 `acpw selfcheck`，结果落在 `selfcheck` 字段（`pass` / `fail` / `skipped`）。想主动追最新版加 `--update`，跳过自检加 `--no-selfcheck`。

`"ok":false` 时按 `notes` 处理，不要自己另想装法：缺 uv、`~/.local/bin` 不在 PATH，或自检没过（完整报告在 stderr）。补全要单独加 `--completion`（会写 `~/.bashrc`）。细节见 [references/install.md](references/install.md)。

## Roles

| 词 | 含义 |
| --- | --- |
| Host | 当前主 agent。拆任务、选 worker、自己跑测试 |
| Worker | `ws://127.0.0.1:PORT/ws?server-key=SECRET` |
| Native | Grok：`grok agent serve` |
| Bridge | Claude / Codex / Cursor：stdio ACP 桥到同一 URL |
| Pool | 一个 daemon 挂多个 stdio child，入口 `ws://127.0.0.1:48190/ws?server-key=SECRET` |

默认端口（高位）：grok `48191`，claude `48192`，codex `48193`，cursor `48194`，pool `48190`。默认监听 `0.0.0.0`，连接一律用 `127.0.0.1`。worker 是 always-approve 且 secret 明文过线，别把这些端口暴露到不可信网络——`acpw selfcheck` 会就此告警。

## Workflow

### Step 1: 探活

```bash
acpw doctor && acpw ls
```

`live` 为真且 `probe` 是 `health` / `ws-401` / `ws-auth` 才可派活。

### Step 2: 备好 worker

```bash
acpw add NAME --url 'ws://127.0.0.1:PORT/ws?server-key=…'   # 已有 serve，登记即可
acpw up grok --cwd "$PWD"                                    # 未启动；已 live 返回 already
acpw pool up --worker claude --worker cursor                 # 可选；一个入口，多 child
```

### Step 3: 写 prompt

一次只派一件可验收的事，写清楚改哪些文件、完成标准是什么。长 prompt 落到文件走 `-f`，别塞进命令行。

### Step 4: 派发

```bash
acpw run grok -f /tmp/task.txt
```

续同一会话加 `--session-id`（只对独立 gateway 可靠；pool 上连接一断 session 就作废，见 [references/pool.md](references/pool.md)）。stdio worker 在 daemon live 时默认走 pool，`--pool` / `--no-pool` 可覆盖；grok 是 native serve，永远走自己的 `48191`。默认超时 600s，可用 `--timeout` 调。

### Step 5: 验收

`ok` 只代表 ACP 回合正常结束，不代表任务做对。Host 必须自己看 diff、跑测试。`stop_reason` 为 `cancelled` 一律当失败处理。

## Commands

| 命令 | 作用 |
| --- | --- |
| `version` | 打印已装版本、Python、包路径（也可 `acpw --version`） |
| `selfcheck` | 八项自检 + mock 往返；有 `fail` 则退出 1（`--no-live` 只查静态项） |
| `ls` | 配置 + 探活 + 进程（别名 `status`） |
| `doctor` | 检查适配器二进制是否在 PATH |
| `up` / `down` | 后台起停（别名 `start` / `stop`） |
| `ping` / `run` | 握手 / 派活（`-p` 或 `-f`，别名 `exec`；`--pool` / `--no-pool`） |
| `pool up` / `pool down` / `pool ls` | 起停、探活 multiplexing daemon（`48190`） |
| `add` / `rm` | 登记、注销 URL |
| `install` / `uninstall` | bash 补全；`--purge` 再停 worker 并删 registry/state |

## Validation

- [ ] `acpw selfcheck` 的 `failed` 为空（装完自动跑过一次）
- [ ] `acpw ls` 里目标 worker `live` 为真
- [ ] `acpw run` 返回的 `stop_reason` 不是 `cancelled`
- [ ] Host 自己看过 diff
- [ ] Host 自己跑过测试并贴出真实结果

## Common Pitfalls

| 问题 | 做法 |
| --- | --- |
| 空跑 `grok agent stdio` | 用 `acpw up grok` |
| 把 worker 回复当作修好了 | 自己跑测试 |
| 密钥进聊天记录 | 只读 `acpw ls`；secret 在 `~/.local/state/acp-workers/` |
| 一个 prompt 塞多件事 | 拆开，逐件派发逐件验收 |
| 把 pool 当启动加速 | 子进程本来就常驻；换来的是一个入口和并发，不是少等进程 |
| pool 上跨两次 `acpw run` 续 `--session-id` | 连接一断绑定就丢；续会话用独立 gateway 加 `--no-pool` |
| daemon 挂了名下 child 一起停 | 要隔离就 `acpw up NAME` |

## References

- [scripts/ensure-acpw.sh](scripts/ensure-acpw.sh) — 幂等装好 CLI，输出一行 JSON
- [references/install.md](references/install.md) — 安装、补全、卸载顺序
- [references/protocol.md](references/protocol.md) — WebSocket URL、ACP 握手序列、stdio 桥、Grok 继承什么
- [references/pool.md](references/pool.md) — 何时用 pool、路由、错误码、与独立 gateway 怎么选
- [assets/registry.example.json](assets/registry.example.json) — registry 结构示例
