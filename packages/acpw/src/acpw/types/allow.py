from pydantic import BaseModel, Field


class AllowResponse(BaseModel):
    ok: bool = True
    allow: list[str] = Field(default_factory=list)
    saved: list[str] | None = None
    source: str
    known: list[str] = Field(default_factory=list)
