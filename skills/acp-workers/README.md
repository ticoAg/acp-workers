# acp-workers

Dispatch coding work over one resident WebSocket that owns many agent processes, and keep verification with the host agent.

`acpw up` starts that socket. `acpw run NAME` opens or resumes a session and returns a `session_id`. Grok, Claude, Codex, and Cursor are children on the same daemon. `--no-pool` is the standalone gateway / `grok agent serve` escape hatch.

[![skills.sh](https://skills.sh/b/ticoAg/acp-workers)](https://skills.sh/ticoAg/acp-workers)

## Install

Install just this skill:

```bash
npx skills add ticoAg/acp-workers --skill acp-workers
```

The skill drives the `acpw` CLI, which is a separate install. The bootstrap script ships with the skill and is idempotent:

```bash
bash scripts/ensure-acpw.sh --completion
```

Equivalent by hand:

```bash
uv tool install "git+https://github.com/ticoAg/acp-workers#subdirectory=packages/acpw"
acpw install
```

## Update

```bash
npx skills update acp-workers
bash scripts/ensure-acpw.sh --update
```

The skill and the CLI carry the same version number. `acpw version` prints what is installed; the bootstrap holds a floor and upgrades the CLI by itself when the skill needs a newer one.

## Requirements

- Python 3.12+ and uv; `~/.local/bin` on `PATH`
- One or more agent binaries: `grok`, `npx` (Claude Code / Codex adapters), `cursor-agent`
- Port `48190` free for the shared WebSocket, or a custom `ACPW_POOL_BIND`

## Use

```bash
acpw selfcheck            # verify the install end to end, mock round trip included
acpw doctor && acpw ls
acpw up grok --cwd "$PWD"
acpw run grok -f /tmp/task.txt
acpw run grok -f /tmp/next.txt --session-id <session_id>
acpw down
```

`acpw run` / `acpw ping` start the socket if needed. A second grok process is `acpw add grok-b --kind grok`.

```bash
acpw up
acpw run claude -f /tmp/task.txt
acpw run cursor -f /tmp/other.txt &
acpw down claude
acpw down
```

`--no-pool` uses that worker's own gateway; `--url` names one socket and also bypasses the pool.

`ok` means the ACP turn ended, not that the task is correct. Read the diff and run the tests before accepting anything.

Workers bind `0.0.0.0` and run always-approve, with the server key in cleartext. Keep these ports off untrusted networks; `acpw selfcheck` reports an `exposure` warning as a reminder.

## Files

| Path | Role |
| --- | --- |
| [SKILL.md](./SKILL.md) | The procedure agents load |
| [scripts/ensure-acpw.sh](./scripts/ensure-acpw.sh) | Idempotent CLI bootstrap; one JSON line on stdout |
| [references/install.md](./references/install.md) | Install, registry/state paths, uninstall order |
| [references/protocol.md](./references/protocol.md) | URL scheme, ACP handshake, stdio bridge, what Grok inherits |
| [references/pool.md](./references/pool.md) | Native WebSocket, session durability, ownership, error codes |
| [assets/registry.example.json](./assets/registry.example.json) | Registry file shape |

## License

MIT
