from enum import Enum

from pydantic import BaseModel, Field


class CheckLevel(str, Enum):
    ok = "ok"
    warn = "warn"
    fail = "fail"


class CheckItem(BaseModel):
    name: str
    level: CheckLevel
    detail: str


class SelfCheckResponse(BaseModel):
    ok: bool
    version: str
    checks: list[CheckItem] = Field(default_factory=list)
    warned: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)
