from pydantic import BaseModel

from acpw.types.pool import PoolStatus
from acpw.types.probe import ListeningHit, ProbeResult
from acpw.types.shared import TransportKind


class WorkerStatus(BaseModel):
    name: str
    kind: str
    enabled: bool
    allowed: bool = True
    transport: TransportKind
    bind: str | None
    live: bool
    probe: str | None
    pid: int | None
    url: str | None
    manual_url: bool
    via: str | None = None


class WorkerStatusList(BaseModel):
    ok: bool = True
    registry: str
    workers: list[WorkerStatus]
    listening_defaults: list[ListeningHit]
    processes: dict[str, list[int]]
    pool: PoolStatus | None = None
    allow: list[str] | None = None
    allow_source: str | None = None


class WorkerStartResponse(BaseModel):
    ok: bool = True
    name: str
    bind: str | None = None
    pid: int | None = None
    already: bool = False
    mode: str | None = None
    live: ProbeResult | None = None
    log: str | None = None
    error: str | None = None


class WorkerStopResponse(BaseModel):
    ok: bool = True
    name: str
    signaled: list[int]
    live: bool = False
