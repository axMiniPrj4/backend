from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.todo import TodoPriority, TodoStatus
from app.schemas.common import ORMModel


def _validate_status(v: str) -> str:
    if v not in TodoStatus.ALL:
        raise ValueError(f"status는 {sorted(TodoStatus.ALL)} 중 하나여야 합니다.")
    return v


def _validate_priority(v: str) -> str:
    if v not in TodoPriority.ALL:
        raise ValueError(f"priority는 {sorted(TodoPriority.ALL)} 중 하나여야 합니다.")
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


class ProjectTodoCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=200)
    priority: str = TodoPriority.MEDIUM

    _p = field_validator("priority")(_validate_priority)


class ProjectTodoUpdateRequest(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=200)
    priority: str | None = None
    status: str | None = None

    @field_validator("priority")
    @classmethod
    def _p(cls, v):
        return _validate_priority(v) if v is not None else v

    @field_validator("status")
    @classmethod
    def _s(cls, v):
        return _validate_status(v) if v is not None else v


class ProjectTodoResponse(ORMModel):
    id: int
    project_id: int
    user_id: int  # 작성자
    author_nickname: str
    content: str
    priority: str
    status: str
    created_at: datetime
    updated_at: datetime
