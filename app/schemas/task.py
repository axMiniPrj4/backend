from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.models.task import TaskStatus
from app.schemas.common import ORMModel


def _validate_status(v: str) -> str:
    if v not in TaskStatus.ALL:
        raise ValueError(f"status는 {sorted(TaskStatus.ALL)} 중 하나여야 합니다.")
    return v


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str | None = None
    assignee_id: int | None = None  # 미지정 시 생성자 자동 할당
    start_date: date
    end_date: date


class TaskUpdateRequest(BaseModel):
    """상태 변경은 전용 엔드포인트(PATCH /status) 사용 — 여기서는 제외."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = None
    assignee_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None


class TaskStatusUpdateRequest(BaseModel):
    status: str

    _s = field_validator("status")(_validate_status)


class TaskResponse(ORMModel):
    id: int
    project_id: int
    title: str
    content: str | None
    status: str
    creator_id: int
    assignee_id: int
    start_date: date
    end_date: date
    created_at: datetime
    updated_at: datetime


class GanttTaskItem(BaseModel):
    id: int
    title: str
    assignee_id: int
    assignee_nickname: str
    start_date: date
    end_date: date
    status: str


class GanttResponse(BaseModel):
    project_id: int
    total_tasks: int
    done_tasks: int
    progress: float  # 완료 Task / 전체 Task × 100
    tasks: list[GanttTaskItem]
