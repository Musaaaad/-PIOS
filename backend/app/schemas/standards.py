from uuid import UUID
from pydantic import BaseModel, ConfigDict


class StandardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    title: str
    source_version: str
    active: bool


class MeasurableElementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    me_id: str
    official_text: str
    eoc: list[str]
    esr: bool
    source_page: int | None
    source_version: str
    owner_role_code: str | None
    active: bool
