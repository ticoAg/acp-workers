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

主 agent 只规划、派发、验收。执行面是本机常驻 ACP WebSocket worker。一律用短命令 `acpw`，一行 JSON。`SKILL_DIR` 是本 skill 目录。

## Install

Skill 和 CLI 分开装。Host 缺 `acpw` 时先装 CLI。

**Skill（给各 agent 扫到 SKILL.md）**

```bash
# GitHub / skills.sh（仓库公开后）
npx skills add ticoAg/acp-workers -g -y

# 本机总库（已经在这儿时）
ln -sfn ~/.agents/skill-library/acp-workers ~/.agents/skills/acp-workers
```

**CLI**

```bash
# 从本目录
uv tool install --editable "$SKILL_DIR"
# 从 GitHub
uv tool install git+https://github.com/ticoAg/acp-workers

acpw install    # bash 补全 → ~/.local/share/bash-completion/completions/acpw 并写入 ~/.bashrc
```

`~/.local/bin` 要在 PATH。新开一个 shell 后 `command -v acpw`。

## Use

### Roles

| 词 | 含义 |
| --- | --- |
| Host | 当前主 agent。拆任务、选 worker、自己跑测试。 |
| Worker | `ws://127.0.0.1:PORT/ws?server-key=SECRET` |
| Native | Grok：`grok agent serve` |
| Bridge | Claude / Codex / Cursor：stdio ACP 接到同一 URL |

默认口（高位）：grok `48191`，claude `48192`，codex `48193`，cursor `48194`。

### Workflow

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
| `uninstall` | 去掉补全；`--purge` 再停 worker 并删 registry/state |

别名：`status`=`ls`，`start`=`up`，`exec`=`run`。

## Uninstall

顺序：先停 worker，再卸 CLI/补全，最后卸 skill。

```bash
acpw down grok          # 每个 live worker 停一次
acpw uninstall          # 补全文件 + ~/.bashrc 标记
acpw uninstall --purge  # 上一项 + 停全部已登记 worker + 删 ~/.config/acp-workers 与 ~/.local/state/acp-workers
uv tool uninstall acpw
npx skills remove acp-workers -g
# 若是本机软链：
rm ~/.agents/skills/acp-workers
```

`uninstall` 不会卸掉 `uv tool` 里的 `acpw` 二进制，最后一步必须 `uv tool uninstall acpw`。

## Pitfalls

| 问题 | 做法 |
| --- | --- |
| 空跑 `grok agent stdio` | `acpw up grok` |
| 把 worker 回复当修好 | 自己跑测试 |
| 密钥进聊天 | 只读 `ls`；secret 在 `~/.local/state/acp-workers/` |

Grok serve 继承 `~/.grok` 权限/MCP/技能。细节见 [references/protocol.md](references/protocol.md)。
