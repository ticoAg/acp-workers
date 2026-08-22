from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    ok: bool = False
    error: str
    name: str | None = None
    known: list[str] = Field(default_factory=list)
