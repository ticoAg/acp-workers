from pydantic import BaseModel, Field

from acpw.types.shared import TransportKind


class Adapter(BaseModel):
    kind: str
    transport: TransportKind
    default_bind: str
    binary: str | None = None
    stdio_argv: list[str] = Field(default_factory=list)
    hidden: bool = False
    notes: str = ""
