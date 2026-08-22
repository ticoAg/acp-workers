from pydantic import BaseModel

from acpw.types.shared import TransportKind


class DoctorAdapter(BaseModel):
    kind: str
    transport: TransportKind
    binary: str | None
    path: str | None
    present: bool
    default_bind: str | None = None


class DoctorResponse(BaseModel):
    ok: bool = True
    adapters: list[DoctorAdapter]
    python: str
