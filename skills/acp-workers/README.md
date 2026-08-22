# acp-workers

Dispatch coding work to resident ACP workers on loopback, and keep verification with the host agent.

Grok runs natively through `grok agent serve`. Claude Code, Codex, and Cursor speak stdio ACP and are bridged onto the same WebSocket URL by `acpw gateway`. Either way the host talks to one address and gets one JSON line back.

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
- Loopback ports 48191–48194 free, or a custom `bind` per worker

## Use

```bash
acpw doctor && acpw ls
acpw up grok --cwd "$PWD"
acpw run grok -f /tmp/task.txt
```

`ok` means the ACP turn ended, not that the task is correct. Read the diff and run the tests before accepting anything.

## Files

| Path | Role |
| --- | --- |
| [SKILL.md](./SKILL.md) | The procedure agents load |
| [scripts/ensure-acpw.sh](./scripts/ensure-acpw.sh) | Idempotent CLI bootstrap; one JSON line on stdout |
| [references/install.md](./references/install.md) | Install, registry/state paths, uninstall order |
| [references/protocol.md](./references/protocol.md) | URL scheme, ACP handshake, stdio bridge, what Grok inherits |
| [assets/registry.example.json](./assets/registry.example.json) | Registry file shape |

## License

MIT
