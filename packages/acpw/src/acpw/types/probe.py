from typing import Any

from pydantic import BaseModel

from acpw.types.shared import ProbeVia


class ProbeResult(BaseModel):
    live: bool
    bind: str | None = None
    via: ProbeVia | None = None
    health: dict[str, Any] | None = None
    http_ws: int | None = None


class ListeningHit(BaseModel):
    kind: str
    bind: str
    ss: str
