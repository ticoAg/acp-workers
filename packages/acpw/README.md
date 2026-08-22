# acpw

CLI for resident [ACP](https://agentclientprotocol.com) workers. A host agent plans and verifies; workers execute over a WebSocket on this machine.

```bash
uv tool install "git+https://github.com/ticoAg/acp-workers#subdirectory=packages/acpw"
acpw install

acpw doctor && acpw ls
acpw up grok --cwd "$PWD"
acpw run grok -f /tmp/task.txt
```

Every command prints one JSON line. `ok` means the ACP turn ended, not that the task is correct.

`acpw run grok` goes through the pool as `grok agent --always-approve --no-leader stdio`. `acpw up grok` / `--no-pool` still start native `serve`. Claude, Codex, and Cursor are stdio-only and use the same pool.

`acpw pool up` runs one daemon on `48190` that owns those children, so a single connection drives several of them concurrently. `acpw run` and `acpw ping` take that path by default whenever a worker has a stdio command, and start the daemon if none is live. `--session-id` continues a pooled conversation across separate invocations. The wire contract is in [`docs/pool-protocol.md`](../../docs/pool-protocol.md).

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
