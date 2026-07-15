from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.models.task import TaskPriority, TaskStatus
from app.schemas.common import ORMModel


def _validate_status(v: str) -> str:
    if v not in TaskStatus.ALL:
        raise ValueError(f"status는 {sorted(TaskStatus.ALL)} 중 하나여야 합니다.")
    return v


def _validate_priority(v: str) -> str:
    if v not in TaskPriority.ALL:
        raise ValueError(f"priority는 {sorted(TaskPriority.ALL)} 중 하나여야 합니다.")
    return v


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str | None = None
    assignee_ids: list[int] | None = None
    start_date: date
    end_date: date
    category: str | None = Field(default="기타", max_length=50)
    work_group: str | None = Field(default="", max_length=100)
    color: str | None = Field(default=None, max_length=20)
    priority: str = TaskPriority.MEDIUM

    @field_validator("priority")
    @classmethod
    def _priority(cls, v):
        return _validate_priority(v)


class TaskUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = None
    assignee_ids: list[int] | None = None
    start_date: date | None = None
    end_date: date | None = None
    category: str | None = Field(default=None, max_length=50)
    work_group: str | None = Field(default=None, max_length=100)
    color: str | None = Field(default=None, max_length=20)
    priority: str | None = Field(default=None, max_length=10)

    @field_validator("priority")
    @classmethod
    def _priority(cls, v):
        return _validate_priority(v) if v is not None else v


class TaskStatusUpdateRequest(BaseModel):
    status: str

    _s = field_validator("status")(_validate_status)


class TaskAssigneeResponse(ORMModel):
    id: int
    nickname: str


class TaskResponse(ORMModel):
    id: int
    project_id: int
    title: str
    content: str | None
    status: str
    priority: str
    creator_id: int
    assignees: list[TaskAssigneeResponse]
    start_date: date
    end_date: date
    category: str
    work_group: str
    color: str | None
    created_at: datetime
    updated_at: datetime


class TaskCommentCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=1000)


class TaskCommentResponse(ORMModel):
    id: int
    task_id: int
    user_id: int
    author_nickname: str
    content: str
    like_count: int
    liked_by_me: bool = False
    created_at: datetime


class TaskHistoryResponse(ORMModel):
    id: int
    task_id: int
    actor_id: int
    actor_nickname: str
    event_type: str
    message: str
    created_at: datetime


class GanttTaskItem(BaseModel):
    id: int
    title: str
    assignees: list[TaskAssigneeResponse]
    start_date: date
    end_date: date
    status: str
    priority: str = TaskPriority.MEDIUM
    category: str = "기타"
    work_group: str = ""
    color: str | None = None


class GanttResponse(BaseModel):
    project_id: int
    total_tasks: int
    done_tasks: int
    progress: float
    tasks: list[GanttTaskItem]
