# acp-workers

Resident [ACP](https://agentclientprotocol.com) workers for host-agent dispatch.

The **host** agent plans and verifies. **Workers** (Grok, Claude Code, Codex, Cursor) execute over a loopback WebSocket.

[![skills.sh](https://skills.sh/b/ticoAg/acp-workers)](https://skills.sh/ticoAg/acp-workers)

## Install

```bash
# skill (Claude / Cursor / Codex / Grok / …)
npx skills add ticoAg/acp-workers -g -y

# CLI
uv tool install git+https://github.com/ticoAg/acp-workers
acpw install    # bash completion
```

From a checkout:

```bash
uv tool install --editable .
acpw install
```

## Usage

```bash
acpw ls
acpw up grok
acpw ping grok
acpw run grok -f task.txt
acpw down grok
```

Default loopback ports: grok `48191`, claude `48192`, codex `48193`, cursor `48194`.

Manual URL:

```bash
acpw add lab --url 'ws://127.0.0.1:48191/ws?server-key=SECRET'
```

## skills.sh layout

This repo is a single-skill package:

- `SKILL.md` at the repository root (`name: acp-workers` matches the directory name)
- optional `scripts/` / `references/` / `assets/` as in the [Agent Skills spec](https://agentskills.io/specification)
- `npx skills add ticoAg/acp-workers` discovers the root `SKILL.md`

There is no extra publish step for skills.sh. Public GitHub + install telemetry is enough.

## License

MIT
