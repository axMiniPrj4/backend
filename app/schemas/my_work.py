from datetime import date

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class MyTaskItem(ORMModel):
    id: int
    project_id: int
    project_title: str
    title: str
    status: str
    start_date: date
    end_date: date
    color: str | None = None


class SearchHit(BaseModel):
    type: str  # project | task | material
    id: int
    title: str
    subtitle: str | None = None
    link_url: str


class SearchResponse(BaseModel):
    items: list[SearchHit] = Field(default_factory=list)
