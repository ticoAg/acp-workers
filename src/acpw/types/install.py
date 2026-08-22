from pydantic import BaseModel, Field


class InstallResponse(BaseModel):
    ok: bool = True
    acpw: str | None
    completion: str | None = None
    bashrc_updated: bool = False
    notes: list[str] = Field(default_factory=list)
