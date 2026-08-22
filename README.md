# acp-workers

本机常驻的 [ACP](https://agentclientprotocol.com) worker，供 host agent 派发任务。

**Host** 负责规划和验收。**Worker**（Grok、Claude Code、Codex、Cursor）通过本机 WebSocket 执行。本仓库同时发布两份产物：教 agent 走这套流程的 skill，以及实现它的 `acpw` CLI。

[![skills.sh](https://skills.sh/b/ticoAg/acp-workers)](https://skills.sh/ticoAg/acp-workers)

## 可用 Skill

### acp-workers

把范围明确的编码任务派给常驻 ACP worker，验收由你自己做。

**适用：**

- 把一件可独立完成的编码任务交给 grok / claude / codex / cursor
- 起一条 WebSocket，底下挂多个 agent 进程（`acpw up`）
- 用上次 `acpw run` 返回的 `session_id` 续对话

**不适用：** grok TUI 咨询或辩论、MCP server 配置、`grok -p`，或把 worker 的自我报告当成验收。

## 安装

```bash
npx skills add ticoAg/acp-workers --skill acp-workers
bash <installed-skill-dir>/scripts/ensure-acpw.sh --completion
```

Skill 自带幂等引导脚本：用 uv 安装 `acpw` CLI，并注册 bash 补全。想手动装：

```bash
uv tool install "git+https://github.com/ticoAg/acp-workers#subdirectory=packages/acpw"
acpw install
```

Registry / state 路径以及卸载顺序见 [`skills/acp-workers/references/install.md`](skills/acp-workers/references/install.md)。

### 让 agent 代装

把下面这段贴给任何有 shell 的编码 agent：

```
把 acp-workers skill 和它的 CLI 装好，然后核验：

1. `npx skills add ticoAg/acp-workers --skill acp-workers`
2. `bash .agents/skills/acp-workers/scripts/ensure-acpw.sh --completion`
   （若你的 harness 把 skill 装到别处，改成那个路径）
3. 两条命令各打印一行 JSON。引导脚本幂等且带版本闸门：`already` 表示已是当前版本，`installed` / `updated` 表示它动手了。`"ok": false` 时按 `notes` 做——不要另想装法，也不要用 pip 装。
4. 脚本会替你跑 `acpw selfcheck`；要的是 `"selfcheck": "pass"`。想看完整报告再自己跑一次 `acpw selfcheck`。`exposure` 告警是预期的——worker 默认绑 `0.0.0.0`。`failed` 里有东西才不正常。
5. 派活之前先读 `.agents/skills/acp-workers/SKILL.md`。

把两行 JSON 原样贴回来。没有它们不要声称成功。
```

## 更新

```bash
npx skills update acp-workers
bash <installed-skill-dir>/scripts/ensure-acpw.sh --update
```

引导脚本也会自愈：把 `acpw version` 和 skill 需要的下限比较，CLI 落后就自行升级。Skill 和 CLI 共用一个版本号，见 [CHANGELOG.md](CHANGELOG.md)。

## 用法

```
起共享 WebSocket，把 /tmp/task.txt 里失败的测试交给 grok
```

```bash
acpw ls && acpw up grok --cwd "$PWD" && acpw run grok -f /tmp/task.txt
```

一条 WebSocket，多个 agent。`acpw up` 在 `48190` 起一个 daemon，底下挂 children。`acpw run` 返回 `session_id`；下次带 `--session-id` 就能续同一段对话。`acpw run` / `acpw ping` 在 daemon 还没起时会自己起一份。

```bash
acpw up
acpw run grok -f /tmp/a.txt
acpw run claude -f /tmp/b.txt &
acpw run grok -f /tmp/c.txt --session-id acpw-s…
acpw down grok
acpw down
```

`--no-pool` 走每个 worker 自己的 gateway 或 `grok agent serve`。细节见 [`skills/acp-workers/references/pool.md`](skills/acp-workers/references/pool.md)。

Worker 默认绑 `0.0.0.0`，客户端拨回环。它们跑 always-approve，`server-key` 明文过线，所以别把这些端口放到不可信网络——`acpw selfcheck` 正是为此告警。

## 仓库结构

```
skills/
  acp-workers/
    SKILL.md          # agent 指令
    AGENTS.md         # 跨 agent 入口
    README.md         # 给人看的 skill 说明
    metadata.json     # version、abstract、references
    scripts/          # ensure-acpw.sh，CLI 引导脚本
    references/       # 安装、线路协议、pool
    assets/           # registry 示例
packages/
  acpw/               # CLI：pyproject、src/acpw、tests
docs/
  pool-protocol.md    # daemon 线路契约，给改 daemon 的人看
skills.sh.json        # skills.sh 分组清单
CHANGELOG.md          # 两份产物共用一条版本线
```

## 开发

```bash
cd packages/acpw
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv tool install --editable .   # 把可热更新的 acpw 放到 PATH
```

测试从不碰真实 agent 二进制；它们驱动隐藏的 `mock` adapter，也就是包内的 echo agent。

## 许可证

MIT
