from pydantic import BaseModel


class VersionResponse(BaseModel):
    ok: bool = True
    version: str
    python: str
    location: str
