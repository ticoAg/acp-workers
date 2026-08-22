from pydantic import BaseModel, Field


class LangResponse(BaseModel):
    ok: bool = True
    lang: str
    saved: str | None = None
    source: str
    supported: list[str] = Field(default_factory=list)
