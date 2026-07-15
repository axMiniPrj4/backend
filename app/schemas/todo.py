from datetime import date, datetime

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
    priority: str = TodoPriority.MEDIUM
    description: str | None = Field(default=None, max_length=1000)
    start_date: date | None = None
    end_date: date | None = None
    color: str | None = Field(default=None, max_length=20)
    status: str = TodoStatus.NOT_DONE

    _p = field_validator("priority")(_validate_priority)
    _s = field_validator("status")(_validate_status)


class TodoUpdateRequest(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=200)
    status: str | None = None
    priority: str | None = None
    description: str | None = Field(default=None, max_length=1000)
    start_date: date | None = None
    end_date: date | None = None
    color: str | None = Field(default=None, max_length=20)

    @field_validator("status")
    @classmethod
    def _s(cls, v):
        return _validate_status(v) if v is not None else v

    @field_validator("priority")
    @classmethod
    def _p(cls, v):
        return _validate_priority(v) if v is not None else v


class TodoResponse(ORMModel):
    id: int
    content: str
    status: str
    priority: str
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    color: str | None = None
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
    user_id: int
    author_nickname: str
    content: str
    priority: str
    status: str
    created_at: datetime
    updated_at: datetime
