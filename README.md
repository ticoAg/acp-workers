# acp-workers

本机一条 [ACP](https://agentclientprotocol.com) WebSocket，底下挂多个 agent 进程。Host 规划、派发、验收；worker 只执行。

仓库同时发布两份产物：[acp-workers skill](skills/acp-workers/)（agent 指令）和 [`acpw` CLI](packages/acpw/)（实现）。可只装其中一份。

[![skills.sh](https://skills.sh/b/ticoAg/acp-workers)](https://skills.sh/ticoAg/acp-workers)

## 架构

Host 只跟 `acpw` 说话。`acpw` 拨 `ws://127.0.0.1:48190`；daemon 翻译三套 id（host / child / session），按需 spawn stdio child。Host 看不到自己打到了哪个进程。

```mermaid
flowchart TB
    Host["Host Agent"]
    CLI["acpw"]
    Host --> CLI

    subgraph Pool["Pool Daemon  port 48190"]
        Mux["ACP mux"]
        subgraph Children["stdio children"]
            Grok["grok"]
            Claude["claude"]
            Codex["codex"]
            Cursor["cursor"]
        end
        Mux --> Grok
        Mux --> Claude
        Mux --> Codex
        Mux --> Cursor
    end

    CLI -->|"ACP WebSocket"| Mux
```

`acpw up` 起这条 socket；`acpw up grok claude` 顺带预热 child；`acpw run` / `acpw ping` 在 daemon 还没起时会自己起一份。`--no-pool` 是每个 worker 自己的 gateway / `grok agent serve` 逃生口。线路契约见 [`docs/pool-protocol.md`](docs/pool-protocol.md)。

公开 `session_id`（`acpw-s` + 16 hex）活过连接、child 和 daemon 重启。续会话带 `--session-id`。三档耐久见 [pool.md](skills/acp-workers/references/pool.md)。

## 支持的 Agent

Registry 名默认等于 kind。同 kind 再开一个进程：`acpw add grok-b --kind grok`。

| 名字 | 框架 | 二进制 | Pool 子进程 | `--no-pool` |
| --- | --- | --- | --- | --- |
| `grok` | [Grok Build](https://x.ai/build) | `grok` | `grok agent --always-approve --no-leader stdio` | `serve` 48191 |
| `claude` | [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | `npx` | [`@agentclientprotocol/claude-agent-acp`](https://www.npmjs.com/package/@agentclientprotocol/claude-agent-acp) | `48192` |
| `codex` | [Codex CLI](https://github.com/openai/codex) | `npx` | [`@agentclientprotocol/codex-acp`](https://www.npmjs.com/package/@agentclientprotocol/codex-acp) | `48193` |
| `cursor` | [Cursor CLI](https://cursor.com/docs/cli/acp) | `cursor-agent` | `cursor-agent acp` | `48194` |

`mock` 是包内 echo agent，给测试用，`acpw ls` 默认不列出。至少一个二进制在 `PATH` 上即可；`acpw doctor` 查缺哪一个。

## 工作流

```mermaid
sequenceDiagram
    autonumber
    participant Host
    participant CLI as acpw
    participant Daemon as Pool Daemon
    participant Child as Worker child

    Host->>CLI: acpw run grok -f task.txt
    CLI->>Daemon: initialize
    CLI->>Daemon: session/new _meta.worker=grok
    Daemon->>Child: spawn + initialize
    Daemon->>Child: session/new
    Daemon-->>CLI: sessionId acpw-s
    CLI->>Daemon: session/prompt
    Daemon->>Child: session/prompt
    Child-->>Daemon: chunks / tool_calls
    Daemon-->>CLI: remap session id
    CLI-->>Host: text + session_id
    Note over Host: ok 只表示回合结束. Host 自己看 diff 和测试.
```

```bash
acpw doctor && acpw ls
acpw up grok --cwd "$PWD"
acpw run grok -f /tmp/task.txt
acpw run claude -f /tmp/other.txt &
acpw run grok -f /tmp/next.txt --session-id acpw-s…
acpw down grok    # 只停一个 child
acpw down         # 停 daemon
```

默认绑 `0.0.0.0:48190`，客户端拨回环。Child 是 always-approve，`server-key` 明文过线——别把端口放到不可信网络。`acpw selfcheck` 会报 `exposure` 告警。

## 安装

```bash
npx skills add ticoAg/acp-workers --skill acp-workers
bash <installed-skill-dir>/scripts/ensure-acpw.sh --completion
```

或只装 CLI：

```bash
uv tool install "git+https://github.com/ticoAg/acp-workers#subdirectory=packages/acpw"
acpw install
```

引导脚本幂等，带版本闸门。路径、卸载顺序见 [install.md](skills/acp-workers/references/install.md)。更新：`npx skills update acp-workers`，再 `ensure-acpw.sh --update`。版本线见 [CHANGELOG.md](CHANGELOG.md)。

<details>
<summary>让 agent 代装</summary>

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

</details>

## 仓库

| 路径 | 作用 |
| --- | --- |
| [`skills/acp-workers/`](skills/acp-workers/) | Skill 载荷：`SKILL.md`、scripts、references |
| [`packages/acpw/`](packages/acpw/) | `acpw` CLI |
| [`docs/pool-protocol.md`](docs/pool-protocol.md) | Daemon 线路契约 |

## 开发

```bash
cd packages/acpw
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv tool install --editable .
```

测试驱动隐藏的 `mock` adapter，不碰真实 agent 二进制，也不碰真实 registry（`ACPW_CONFIG_DIR` / `ACPW_STATE_DIR` + `free_port()`）。

## 许可证

MIT
