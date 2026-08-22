# Changelog

Versions cover both artifacts in this repository: the `acp-workers` skill and the `acpw` CLI. They are released together, so `packages/acpw/pyproject.toml`, `skills/acp-workers/metadata.json`, and the `metadata.version` field in `skills/acp-workers/SKILL.md` always carry the same number.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0]

### Added

- `acpw selfcheck`: eight checks over the CLI, PATH, uv, registry, state directory, shell completion, adapter binaries, and a live round trip through a throwaway mock worker. Exits 1 when anything fails; `--no-live` keeps it to the static checks.
- `scripts/ensure-acpw.sh` runs the self-check after installing and reports it in the `selfcheck` field. A failure sets `"ok":false`, prints the full report on stderr, and exits 1. `--no-selfcheck` opts out.

### Fixed

- `ACPW_CONFIG_DIR` and `ACPW_STATE_DIR` were read once at import, so setting them afterwards had no effect and the test suite wrote to the caller's real registry. Paths now resolve per call.

## [0.1.1]

### Fixed

- `SKILL.md` frontmatter failed to parse as YAML: the unquoted `description` contains `USE FOR:`, which YAML reads as a nested mapping, so `npx skills add` skipped the skill and reported "No skills found". Quoted the scalar. CI now parses every skill's frontmatter.

## [0.1.0]

### Added

- `acpw` CLI: `ls`, `doctor`, `add`, `rm`, `up`, `down`, `ping`, `run`, `install`, `uninstall`, `version`. Every command prints one JSON line.
- Native Grok worker via `grok agent serve`; stdio ACP bridge for Claude Code, Codex, and Cursor on ports 48191–48194.
- `acp-workers` skill: dispatch workflow, wire protocol reference, install reference, example registry.
- `scripts/ensure-acpw.sh`: idempotent CLI bootstrap with a version floor, `--update`, `--force`, and `--completion`.

[Unreleased]: https://github.com/ticoAg/acp-workers/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/ticoAg/acp-workers/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/ticoAg/acp-workers/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/ticoAg/acp-workers/releases/tag/v0.1.0
