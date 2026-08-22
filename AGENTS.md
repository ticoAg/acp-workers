# AGENTS.md

Guidance for AI coding agents working **on this repository**. To *use* the skill instead, read [skills/acp-workers/SKILL.md](skills/acp-workers/SKILL.md).

## Repository Overview

Two artifacts from one tree: the `acp-workers` skill (instructions agents load) and the `acpw` CLI (the Python package those instructions drive). They ship separately — a user can install one without the other — so neither may depend on the other's location on disk.

## Layout

```
skills/{skill-name}/     # kebab-case; one directory per skill
  SKILL.md               # required
  AGENTS.md              # cross-agent entry point, points at SKILL.md
  README.md              # human-facing
  metadata.json          # version, organization, abstract, references
  scripts/               # executables that ship with the skill
  references/            # loaded on demand, one level deep from SKILL.md
  assets/                # example data files
packages/{package}/      # code, tests, and lockfile
docs/                    # contracts for people changing the code, not skill payload
skills.sh.json           # skills.sh grouping manifest
.github/workflows/       # CI
```

## Skill Conventions

- `name` in the SKILL.md frontmatter must equal the directory name.
- Keep `SKILL.md` under 500 lines. Anything rare or long goes to `references/` and is linked, not inlined.
- The description is the router: lead with the action, then `USE FOR:` triggers and `DO NOT USE FOR:` exclusions naming the sibling skill that owns them.
- Adding a skill means adding it to `skills.sh.json` as well.
- `npx skills add` copies the skill directory — `SKILL.md`, `AGENTS.md`, `README.md`, `references/`, `scripts/`, `assets/`, executable bits intact. `metadata.json` is consumed by the installer and does not land on disk, so nothing may depend on it at runtime. Nothing outside `skills/<name>/` ships at all.
- Frontmatter is parsed as YAML by the installer. Quote any scalar containing `: `, or the skill is silently skipped with "No skills found".
- Scripts: `#!/bin/bash` with `set -euo pipefail`, executable bit set, kebab-case name. Progress goes to stderr, one machine-readable JSON line to stdout. Make them idempotent — an agent may run them on every invocation.

## CLI Conventions (`packages/acpw`)

- Types live in `src/acpw/types/` (Pydantic SSOT). Business code imports from `acpw.types`, never deep paths.
- The CLI never prints prose. One `BaseModel` per command, serialized with `model_dump_json()`.
- Adapter defaults (binary, `stdio_argv`, default bind) live in `src/acpw/adapters.py`.
- The package must not resolve paths relative to the repository; `references/` and `assets/` are skill payload, not runtime data.
- Adding or renaming a command means updating the command table in `SKILL.md` too.
- The pool daemon answers to [`docs/pool-protocol.md`](docs/pool-protocol.md). Change one and change the other in the same commit; the daemon is the only thing a host talks to, and a host cannot see which child it reached.
- Ids never cross: host ids, child ids, and session ids are three separate spaces the daemon translates between. Children choose their own session ids and two of them can pick the same string, so nothing may key a table on a child-supplied id.
- Tests must not touch a real registry. Set `ACPW_CONFIG_DIR` and `ACPW_STATE_DIR`, and take ports from `free_port()` rather than the defaults.

## Releasing

The skill and the CLI share one version number. A release bumps all of these together:

| File | Field |
| --- | --- |
| `packages/acpw/pyproject.toml` | `version` |
| `skills/acp-workers/metadata.json` | `version` |
| `skills/acp-workers/SKILL.md` | `metadata.version` in the frontmatter |
| `CHANGELOG.md` | move `Unreleased` entries under the new version |

`__version__` is read from installed package metadata, so it needs no edit. Raise `required_version` in `skills/acp-workers/scripts/ensure-acpw.sh` only when the skill's instructions start depending on a newer CLI; CI rejects a floor above the released version. Tag as `vX.Y.Z` so the CHANGELOG links resolve.

## Before Pushing

```bash
cd packages/acpw && uv run ruff check . && uv run ruff format --check . && uv run pytest
```
