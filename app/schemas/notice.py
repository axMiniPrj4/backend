from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.notice import NoticeCategory
from app.schemas.common import ORMModel


def _validate_category(v: str) -> str:
    if v not in NoticeCategory.ALL:
        raise ValueError(f"category는 {sorted(NoticeCategory.ALL)} 중 하나여야 합니다.")
    return v


class NoticeCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)
    category: str = NoticeCategory.SERVICE
    pinned: bool = False

    _c = field_validator("category")(_validate_category)


class NoticeUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1)
    category: str | None = None
    pinned: bool | None = None

    @field_validator("category")
    @classmethod
    def _c(cls, v):
        return _validate_category(v) if v is not None else v


class NoticeResponse(ORMModel):
    id: int
    title: str
    body: str
    category: str
    pinned: bool
    created_at: datetime
    updated_at: datetime
