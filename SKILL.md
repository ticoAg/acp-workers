---
name: acp-workers
description: Dispatch coding work to resident ACP workers over loopback WebSocket via the acpw CLI (Grok native serve; Claude/Codex/Cursor stdio bridged). Host agent plans, scopes, and verifies; workers execute. USE FOR: acpw ls/up/run, grok agent serve, ACP websocket, 常驻 ACP, 派发给 grok/claude/codex/cursor, 服务发现. DO NOT USE FOR: grok TUI consult/debate (grok-build-connector); MCP servers; grok -p; grok agent stdio in a tty; treating worker output as verified.
license: MIT
compatibility: Requires Python 3.12+ and uv. CLI name is acpw.
metadata:
  author: ticoAg
  version: "0.1.0"
---

# ACP Workers

主 agent 只规划、派发、验收。执行面是本机常驻 ACP WebSocket worker。一律用短命令 `acpw`，一行 JSON。

```bash
uv tool install --editable "$SKILL_DIR"   # 一次
acpw install                              # bash 补全
acpw ls
acpw up grok
acpw ping grok
acpw run grok -f /tmp/task.txt
acpw down grok
```

`SKILL_DIR` 是本 skill 目录。已安装则直接 `acpw`。

## Roles

| 词 | 含义 |
| --- | --- |
| Host | 当前主 agent。拆任务、选 worker、自己跑测试。 |
| Worker | `ws://127.0.0.1:PORT/ws?server-key=SECRET` |
| Native | Grok：`grok agent serve` |
| Bridge | Claude / Codex / Cursor：stdio ACP 接到同一 URL |

默认口（高位）：grok `48191`，claude `48192`，codex `48193`，cursor `48194`。

## Workflow

1. `acpw doctor` 然后 `acpw ls`。`live` 且 `probe` 为 `health`/`ws-401`/`ws-auth` 才可派。
2. 已有 serve：`acpw add NAME --url 'ws://127.0.0.1:PORT/ws?server-key=…'`
3. 未启动：`acpw up grok --cwd "$PWD"`（已 live 则 `already`）。
4. Prompt 写成一件可验收的事，再 `acpw run grok -f /tmp/task.txt`。续聊 `--session-id`。
5. `ok` 只表示 ACP 回合结束。Host 必须自己看 diff、跑测试。`stop_reason` 为 cancelled 当失败。

## Commands

| 命令 | 作用 |
| --- | --- |
| `ls` | 配置 + 探活 + 进程 |
| `up` / `down` | 后台起停 |
| `ping` / `run` | 握手 / 派活（`-p` 或 `-f`） |
| `add` / `rm` | 登记 URL |
| `install` | bash 补全 |

别名：`status`=`ls`，`start`=`up`，`exec`=`run`。

## Pitfalls

| 问题 | 做法 |
| --- | --- |
| 空跑 `grok agent stdio` | `acpw up grok` |
| 把 worker 回复当修好 | 自己跑测试 |
| 密钥进聊天 | 只读 `ls`；secret 在 `~/.local/state/acp-workers/` |

Grok serve 继承 `~/.grok` 权限/MCP/技能。细节见 [references/protocol.md](references/protocol.md)。
