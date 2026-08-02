from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel):
    items: list[dict]
    total: int
    limit: int = Field(ge=1, le=500)
    offset: int = Field(ge=0)
