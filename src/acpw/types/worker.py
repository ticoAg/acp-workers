from pydantic import BaseModel

from acpw.types.probe import ListeningHit, ProbeResult
from acpw.types.shared import TransportKind


class WorkerStatus(BaseModel):
    name: str
    kind: str
    enabled: bool
    transport: TransportKind
    bind: str | None
    live: bool
    probe: str | None
    pid: int | None
    url: str | None
    manual_url: bool


class WorkerStatusList(BaseModel):
    ok: bool = True
    registry: str
    workers: list[WorkerStatus]
    listening_defaults: list[ListeningHit]
    processes: dict[str, list[int]]


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
