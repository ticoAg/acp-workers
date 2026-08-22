# acpw

本机常驻 [ACP](https://agentclientprotocol.com) worker 的 CLI。Host agent 规划和验收；worker 通过本机 WebSocket 执行。

```bash
uv tool install "git+https://github.com/ticoAg/acp-workers#subdirectory=packages/acpw"
acpw install

acpw doctor && acpw ls
acpw up grok --cwd "$PWD"
acpw run grok -f /tmp/task.txt
acpw run grok -f /tmp/next.txt --session-id <session_id>
acpw down
```

每条命令打印一行 JSON。`ok` 表示 ACP 回合结束，不表示任务做对。

`--help` 和 CLI 提示支持 `en-US`、`zh-CN`、`zh-TW`：

```bash
acpw --lang zh-CN --help
acpw lang set zh-CN      # 写入 ~/.config/acp-workers/config.json
acpw lang                # 查看当前语言
```

一次调用还可用 `ACPW_LANG`。字段名仍是英文。

原生模式是 `48190` 上的一条 WebSocket，底下挂多个 agent 进程。`acpw up` 起它；`acpw run NAME` 开或续一段会话；`acpw down NAME` 停一个 child；`acpw down` 停这条 socket。Pool 里的 grok 是 `grok agent --always-approve --no-leader stdio`。`--no-pool` 是独立 gateway / `grok agent serve` 逃生口。线路契约见 [`docs/pool-protocol.md`](../../docs/pool-protocol.md)。

面向 agent 的指令作为 `acp-workers` skill 与本包一同发布：见仓库里的 [`skills/acp-workers/`](../../skills/acp-workers/)，或用 `npx skills add ticoAg/acp-workers --skill acp-workers` 安装。

## 开发

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

测试驱动隐藏的 `mock` adapter，也就是包内的 echo agent。不需要真实 agent 二进制。

## 许可证

MIT
