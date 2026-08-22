# acp-workers

Python package `acpw`, CLI `acpw`. Types live in `src/acpw/types/` (Pydantic SSOT). Business code imports from `acpw.types`, not deep paths.

| Path | Role |
| --- | --- |
| `src/acpw/types/` | Cross-module JSON/config/CLI shapes |
| `src/acpw/cli.py` | Typer entry |
| `src/acpw/service.py` | start/stop/exec/ping |
| `src/acpw/gateway.py` | stdio ↔ WebSocket |
| `SKILL.md` | Agent instructions; `name` matches this directory |
