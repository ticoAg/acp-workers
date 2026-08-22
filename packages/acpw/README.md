# acpw

CLI for resident [ACP](https://agentclientprotocol.com) workers. A host agent plans and verifies; workers execute over a WebSocket on this machine.

```bash
uv tool install "git+https://github.com/ticoAg/acp-workers#subdirectory=packages/acpw"
acpw install

acpw doctor && acpw ls
acpw up grok --cwd "$PWD"
acpw run grok -f /tmp/task.txt
acpw run grok -f /tmp/next.txt --session-id <session_id>
acpw down
```

Every command prints one JSON line. `ok` means the ACP turn ended, not that the task is correct.

Native mode is one WebSocket on `48190` that owns many agent processes. `acpw up` starts it; `acpw run NAME` opens or resumes a session; `acpw down NAME` stops one child; `acpw down` stops the socket. Grok in the pool is `grok agent --always-approve --no-leader stdio`. `--no-pool` is the standalone gateway / `grok agent serve` escape hatch. The wire contract is in [`docs/pool-protocol.md`](../../docs/pool-protocol.md).

The agent-facing instructions ship alongside this package as the `acp-workers` skill: see [`skills/acp-workers/`](../../skills/acp-workers/) in the repository, or install it with `npx skills add ticoAg/acp-workers --skill acp-workers`.

## Development

```bash
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

Tests drive the hidden `mock` adapter, an in-package echo agent. No real agent binary is needed.

## License

MIT
