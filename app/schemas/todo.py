from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.todo import TodoStatus
from app.schemas.common import ORMModel


def _validate_status(v: str) -> str:
    if v not in TodoStatus.ALL:
        raise ValueError(f"status는 {sorted(TodoStatus.ALL)} 중 하나여야 합니다.")
    return v


class TodoCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=200)


class TodoUpdateRequest(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=200)
    status: str | None = None

    @field_validator("status")
    @classmethod
    def _s(cls, v):
        return _validate_status(v) if v is not None else v


class TodoResponse(ORMModel):
    id: int
    content: str
    status: str
    created_at: datetime
    updated_at: datetime
