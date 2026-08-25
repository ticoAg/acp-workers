from typing import Any

from pydantic import BaseModel, Field


class ToolCallOut(BaseModel):
    kind: str
    title: str | None = None
    status: str | None = None
    name: str | None = None


class ExecParams(BaseModel):
    name: str
    prompt: str
    cwd: str
    session_id: str | None = None
    url: str | None = None
    timeout: float = 600


class ExecResponse(BaseModel):
    ok: bool
    name: str
    session_id: str | None = None
    stop_reason: str | None = None
    text: str | None = None
    tool_calls: list[ToolCallOut] = Field(default_factory=list)
    error: str | None = None


class PingResponse(BaseModel):
    ok: bool
    name: str
    protocol_version: Any = None
    agent_version: str | None = None
    agent_info: dict[str, Any] | None = None
    error: str | None = None


class SessionInfo(BaseModel):
    session_id: str
    worker: str
    cwd: str = ""
    live: bool = False
    held: bool = False


class SessionListResponse(BaseModel):
    ok: bool = True
    sessions: list[SessionInfo] = Field(default_factory=list)


class SessionDeleteResponse(BaseModel):
    ok: bool = True
    session_id: str


class SessionPruneResponse(BaseModel):
    ok: bool = True
    deleted: int = 0
    kept: int = 0
