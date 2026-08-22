from pydantic import BaseModel, Field


class Worker(BaseModel):
    kind: str
    enabled: bool = True
    bind: str | None = None
    url: str | None = None
    stdio_argv: list[str] | None = None


class Registry(BaseModel):
    workers: dict[str, Worker] = Field(default_factory=dict)


class WorkerCreateParams(BaseModel):
    name: str
    kind: str | None = None
    url: str | None = None
    bind: str | None = None


class WorkerDeleted(BaseModel):
    ok: bool = True
    removed: str


class WorkerRegistered(BaseModel):
    ok: bool = True
    saved: str
    kind: str
    bind: str | None = None
    url_set: bool = False
