# acp-workers

Resident [ACP](https://agentclientprotocol.com) workers for host-agent dispatch.

The **host** agent plans and verifies. **Workers** (Grok, Claude Code, Codex, Cursor) execute over a loopback WebSocket.

[![skills.sh](https://skills.sh/b/ticoAg/acp-workers)](https://skills.sh/ticoAg/acp-workers)

Install, use, and uninstall procedures live in [`SKILL.md`](SKILL.md) (the copy agents load). Short version:

```bash
npx skills add ticoAg/acp-workers -g -y
uv tool install git+https://github.com/ticoAg/acp-workers
acpw install
acpw ls && acpw up grok && acpw run grok -f task.txt
acpw uninstall --purge
uv tool uninstall acpw
npx skills remove acp-workers -g
```

From a checkout: `uv tool install --editable .` then `acpw install`.

## skills.sh layout

This repo is a single-skill package:

- `SKILL.md` at the repository root (`name: acp-workers` matches the directory name)
- optional `scripts/` / `references/` / `assets/` as in the [Agent Skills spec](https://agentskills.io/specification)
- `npx skills add ticoAg/acp-workers` discovers the root `SKILL.md`

There is no extra publish step for skills.sh. Public GitHub + install telemetry is enough.

## License

MIT
