from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.models.project import ProjectPriority, ProjectStatus
from app.schemas.common import ORMModel


def _validate_priority(v: str) -> str:
    if v not in ProjectPriority.ALL:
        raise ValueError(f"priority는 {sorted(ProjectPriority.ALL)} 중 하나여야 합니다.")
    return v


def _validate_status(v: str) -> str:
    if v not in ProjectStatus.ALL:
        raise ValueError(f"status는 {sorted(ProjectStatus.ALL)} 중 하나여야 합니다.")
    return v


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    priority: str = ProjectPriority.MEDIUM
    status: str = ProjectStatus.PLANNED
    start_date: date | None = None
    end_date: date | None = None

    _p = field_validator("priority")(_validate_priority)
    _s = field_validator("status")(_validate_status)


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    priority: str | None = None
    status: str | None = None
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("priority")
    @classmethod
    def _p(cls, v):
        return _validate_priority(v) if v is not None else v

    @field_validator("status")
    @classmethod
    def _s(cls, v):
        return _validate_status(v) if v is not None else v


class ProjectJoinRequest(BaseModel):
    code: str = Field(min_length=1)


class LeaderDelegateRequest(BaseModel):
    user_id: int


class ProjectResponse(ORMModel):
    id: int
    name: str
    description: str | None
    code: str
    priority: str
    status: str
    start_date: date | None
    end_date: date | None
    created_at: datetime


class ProjectListItemResponse(ORMModel):
    """목록용 — 참여 코드는 상세에서만 노출."""

    id: int
    name: str
    description: str | None
    priority: str
    status: str
    start_date: date | None
    end_date: date | None
    created_at: datetime


class ProjectCodeResponse(BaseModel):
    code: str


class MemberResponse(BaseModel):
    user_id: int
    name: str
    nickname: str
    role: str
    joined_at: datetime
