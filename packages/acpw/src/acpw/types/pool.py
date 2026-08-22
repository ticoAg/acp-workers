from pydantic import BaseModel, Field


class PoolWorker(BaseModel):
    name: str
    kind: str
    alive: bool
    pid: int | None = None
    sessions: int = 0


class PoolStatus(BaseModel):
    ok: bool = True
    live: bool
    bind: str
    url: str
    pid: int | None = None
    workers: list[PoolWorker] = Field(default_factory=list)
    sessions: int = 0
    log: str | None = None


class PoolStartResponse(BaseModel):
    ok: bool = True
    bind: str
    url: str
    pid: int | None = None
    already: bool = False
    log: str | None = None
    workers: list[PoolWorker] = Field(default_factory=list)


class PoolStopResponse(BaseModel):
    ok: bool = True
    signaled: list[int] = Field(default_factory=list)
    live: bool = False
