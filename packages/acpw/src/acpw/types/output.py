from pydantic import BaseModel, Field


class OutputResponse(BaseModel):
    ok: bool = True
    output: str
    saved: str | None = None
    source: str
    supported: list[str] = Field(default_factory=list)
