# acp-workers

ACP Workers skill 的跨 agent 入口。完整流程见 [SKILL.md](./SKILL.md)。

用户要把编码任务交给 grok / claude / codex / cursor、起一条底下挂多个 agent 的 WebSocket（`acpw up`）、或用 `session_id` 续对话时，使用本 skill。

不要用于 grok TUI 咨询或辩论、MCP server 配置、`grok -p`，或在 tty 里手工跑 `grok agent stdio`。

## 要求

- Python 3.12+ 和 [uv](https://docs.astral.sh/uv/)
- `PATH` 上有 `acpw` CLI —— 跑 `bash scripts/ensure-acpw.sh`，细节见 [references/install.md](./references/install.md)
- 至少一个 adapter 能碰到的 agent 二进制：`grok`、`npx` 或 `cursor-agent`

## 流程

1. 读 [SKILL.md](./SKILL.md)。
2. `bash scripts/ensure-acpw.sh`，然后 `acpw doctor && acpw ls`。原生路径是 `pool.live` / `via: pool`。
3. `acpw up` 起共享 WebSocket；`acpw run NAME` 在需要时会自己起，并返回 `session_id`。续会话带 `--session-id`。`--no-pool` 是独立 gateway / serve 逃生口。见 [references/pool.md](./references/pool.md)。
4. 写一件可验收的任务，用 `acpw run` 派发。
5. 自己验收：看 diff、跑测试。Worker 的报告不是证据。

## 安装

```bash
npx skills add ticoAg/acp-workers --skill acp-workers
```

手动装进项目：

```bash
mkdir -p .agents/skills
cp -R <acp-workers-repo>/skills/acp-workers .agents/skills/
```
