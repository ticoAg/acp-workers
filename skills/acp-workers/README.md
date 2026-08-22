# acp-workers

Dispatch coding work to resident ACP workers on this machine, and keep verification with the host agent.

Grok runs natively through `grok agent serve`. Claude Code, Codex, and Cursor speak stdio ACP and are bridged onto the same WebSocket URL by `acpw gateway`. Either way the host talks to one address and gets one JSON line back.

The stdio workers share one resident pool daemon by default (`acpw run` / `acpw ping` start it if none is live), so a host drives several of them concurrently over a single connection instead of one port per worker. `acpw pool up` pre-warms children. Grok stays on its own `grok agent serve` gateway.

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
- One or more agent binaries: `grok` (native), `npx` (Claude Code / Codex adapters), `cursor-agent`
- Ports 48191–48194 free, plus 48190 for the pool, or a custom `bind` per worker

## Use

```bash
acpw selfcheck            # verify the install end to end, mock round trip included
acpw doctor && acpw ls
acpw up grok --cwd "$PWD"
acpw run grok -f /tmp/task.txt
```

Stdio workers go through the pool by default. The daemon starts on first `run` / `ping`; `acpw pool up` is optional pre-warm. `--session-id` continues a pooled conversation across invocations.

```bash
acpw run claude -f /tmp/task.txt      # starts the pool if needed
acpw ping cursor                      # reaches the cursor child, not the daemon
acpw pool up --worker claude --worker cursor
acpw pool ls && acpw pool down
```

`--no-pool` uses that worker's own gateway; `--pool` forces the pool. Grok is never pooled. `--url` names one socket and also bypasses the pool.

`ok` means the ACP turn ended, not that the task is correct. Read the diff and run the tests before accepting anything.

Workers bind `0.0.0.0` and run always-approve, with the server key in cleartext. Keep these ports off untrusted networks; `acpw selfcheck` reports an `exposure` warning as a reminder.

## Files

| Path | Role |
| --- | --- |
| [SKILL.md](./SKILL.md) | The procedure agents load |
| [scripts/ensure-acpw.sh](./scripts/ensure-acpw.sh) | Idempotent CLI bootstrap; one JSON line on stdout |
| [references/install.md](./references/install.md) | Install, registry/state paths, uninstall order |
| [references/protocol.md](./references/protocol.md) | URL scheme, ACP handshake, stdio bridge, what Grok inherits |
| [references/pool.md](./references/pool.md) | Default pool path, session durability, ownership, error codes |
| [assets/registry.example.json](./assets/registry.example.json) | Registry file shape |

## License

MIT
