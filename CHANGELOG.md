# Changelog

Versions cover both artifacts in this repository: the `acp-workers` skill and the `acpw` CLI. They are released together, so `packages/acpw/pyproject.toml`, `skills/acp-workers/metadata.json`, and the `metadata.version` field in `skills/acp-workers/SKILL.md` always carry the same number.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0]

### Added

- `acpw` CLI: `ls`, `doctor`, `add`, `rm`, `up`, `down`, `ping`, `run`, `install`, `uninstall`, `version`. Every command prints one JSON line.
- Native Grok worker via `grok agent serve`; stdio ACP bridge for Claude Code, Codex, and Cursor on ports 48191–48194.
- `acp-workers` skill: dispatch workflow, wire protocol reference, install reference, example registry.
- `scripts/ensure-acpw.sh`: idempotent CLI bootstrap with a version floor, `--update`, `--force`, and `--completion`.

[Unreleased]: https://github.com/ticoAg/acp-workers/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ticoAg/acp-workers/releases/tag/v0.1.0
