# acp-workers

Resident [ACP](https://agentclientprotocol.com) workers for host-agent dispatch.

The **host** agent plans and verifies. **Workers** (Grok, Claude Code, Codex, Cursor) execute over a WebSocket on this machine. This repository ships the skill that teaches agents the workflow, plus the `acpw` CLI that implements it.

[![skills.sh](https://skills.sh/b/ticoAg/acp-workers)](https://skills.sh/ticoAg/acp-workers)

## Available Skills

### acp-workers

Dispatch a scoped coding task to a resident ACP worker and verify the result yourself.

**Use when:**

- Handing a self-contained coding task to grok / claude / codex / cursor in the background
- Listing, starting, or stopping resident workers (`acpw ls` / `up` / `down`)
- Registering an already-running `grok agent serve` as a worker
- Driving several stdio workers concurrently over one connection (`acpw run` starts the pool if needed)

**Not for:** grok TUI consultation or debate, MCP server setup, `grok -p`, or treating a worker's self-report as verification.

## Installation

```bash
npx skills add ticoAg/acp-workers --skill acp-workers
bash <installed-skill-dir>/scripts/ensure-acpw.sh --completion
```

The skill ships an idempotent bootstrap that installs the `acpw` CLI with uv and registers bash completion. To do it by hand instead:

```bash
uv tool install "git+https://github.com/ticoAg/acp-workers#subdirectory=packages/acpw"
acpw install
```

Registry/state locations and the uninstall order live in [`skills/acp-workers/references/install.md`](skills/acp-workers/references/install.md).

### Have an agent install it

Paste this to any coding agent with shell access:

```
Install the acp-workers skill and its CLI, then verify:

1. `npx skills add ticoAg/acp-workers --skill acp-workers`
2. `bash .agents/skills/acp-workers/scripts/ensure-acpw.sh --completion`
   (if your harness installs skills elsewhere, use that path)
3. Both commands print one JSON line. The bootstrap is idempotent and
   version-aware: `already` means it was current, `installed` / `updated`
   mean it acted. On `"ok": false`, do what `notes` says — do not invent
   another install method, and do not pip install anything.
4. The bootstrap runs `acpw selfcheck` for you; `"selfcheck": "pass"` is
   what you want. Run `acpw selfcheck` again yourself if you want the full
   report. An `exposure` warning is expected — workers bind 0.0.0.0 by
   design. Anything in `failed` is not.
5. Read `.agents/skills/acp-workers/SKILL.md` before dispatching work.

Report the two JSON lines back verbatim. Do not claim success without them.
```

## Updating

```bash
npx skills update acp-workers
bash <installed-skill-dir>/scripts/ensure-acpw.sh --update
```

The bootstrap also self-heals: it compares `acpw version` against the floor the skill needs and upgrades on its own when the CLI is behind. The skill and the CLI ship under one version number; see [CHANGELOG.md](CHANGELOG.md).

## Usage

```
Start a grok worker in this repo and hand it the failing test in /tmp/task.txt
```

```bash
acpw ls && acpw up grok --cwd "$PWD" && acpw run grok -f /tmp/task.txt
```

One worker, one port. Stdio workers (claude, cursor, codex, mock) go through the
pool by default: a single daemon on `48190` holding the children, so one
connection drives all of them. `acpw run` / `acpw ping` start that daemon if
none is live. `acpw pool up` pre-warms children.

```bash
acpw run claude -f /tmp/a.txt &
acpw run cursor -f /tmp/b.txt &
```

`--no-pool` uses a per-worker gateway; `--pool` forces the pool. Grok is native
`serve` and always keeps its own port. An explicit `--url` also bypasses the
pool. `--session-id` continues a pooled conversation across separate `acpw run`
invocations. Details in [`skills/acp-workers/references/pool.md`](skills/acp-workers/references/pool.md).

Workers bind `0.0.0.0` by default and clients dial loopback. They run always-approve and
the server key travels in cleartext, so do not expose these ports to a network you do not
trust — `acpw selfcheck` warns about exactly this.

## Repository Structure

```
skills/
  acp-workers/
    SKILL.md          # agent instructions
    AGENTS.md         # cross-agent entry point
    README.md         # human-facing skill docs
    metadata.json     # version, abstract, references
    scripts/          # ensure-acpw.sh, the CLI bootstrap
    references/       # install, wire protocol, pool
    assets/           # example registry file
packages/
  acpw/               # the CLI: pyproject, src/acpw, tests
docs/
  pool-protocol.md    # daemon wire contract, for people changing the daemon
skills.sh.json        # skills.sh grouping manifest
CHANGELOG.md          # one version line for both artifacts
```

## Development

```bash
cd packages/acpw
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv tool install --editable .   # put a live acpw on PATH
```

Tests never touch a real agent binary; they drive the hidden `mock` adapter, an in-package echo agent.

## License

MIT
