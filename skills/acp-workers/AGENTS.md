# acp-workers

Cross-agent entry point for the ACP Workers skill. The full procedure is in [SKILL.md](./SKILL.md).

Use this skill when the user asks to hand a coding task to grok / claude / codex / cursor in the background, to list or start or stop resident ACP workers, to reuse a `grok agent serve` that is already running, or to drive several stdio workers at once through the pool daemon (`acpw run` starts it if needed).

Do not use it for grok TUI consultation or debate, MCP server configuration, `grok -p`, or running `grok agent stdio` by hand in a tty.

## Requirements

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- The `acpw` CLI on `PATH` — run `bash scripts/ensure-acpw.sh`, details in [references/install.md](./references/install.md)
- At least one agent binary the adapters can reach: `grok`, `npx`, or `cursor-agent`

## Procedure

1. Read [SKILL.md](./SKILL.md).
2. `bash scripts/ensure-acpw.sh`, then `acpw doctor && acpw ls`. For grok / `--no-pool`, only dispatch to a worker that is `live`. For stdio workers, `acpw ping NAME` (or `acpw run`) starts the pool if needed.
3. Start or register a native serve worker with `acpw up` / `acpw add`. Stdio workers go through the pool by default — `acpw run` starts the daemon if none is live. `acpw pool up` pre-warms children; `--no-pool` keeps a per-worker gateway. See [references/pool.md](./references/pool.md).
4. Write one acceptance-shaped task, dispatch with `acpw run`.
5. Verify yourself: read the diff, run the tests. A worker's report is not evidence.

## Install

```bash
npx skills add ticoAg/acp-workers --skill acp-workers
```

Manual project install:

```bash
mkdir -p .agents/skills
cp -R <acp-workers-repo>/skills/acp-workers .agents/skills/
```
