from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel
from app.schemas.doc import ArchiveDocResponse, DocVersionResponse
from app.schemas.project import MemberResponse, ProjectResponse
from app.schemas.task import TaskResponse


class AnswerTemplateCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)


class AnswerTemplateUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1)


class AnswerTemplateResponse(ORMModel):
    id: int
    title: str
    content: str
    created_by: int
    created_at: datetime
    updated_at: datetime


class AdminProjectDetailResponse(ProjectResponse):
    members: list[MemberResponse] = []
    tasks: list[TaskResponse] = []


class AdminProjectListItemResponse(ProjectResponse):
    """목록용 — N+1 없이 진행률·팀장 요약."""

    task_count: int = 0
    task_done_count: int = 0
    leader_name: str | None = None
    member_count: int = 0


class AdminStatsResponse(BaseModel):
    users_total: int
    projects_total: int
    projects_in_progress: int
    inquiries_pending: int
    materials_total: int
    notices_total: int


class AdminMemberAddRequest(BaseModel):
    user_id: int


class AdminMaterialProjectRequest(BaseModel):
    """자료를 프로젝트에 연결( project_id )하거나 공통으로 분리( null )."""

    project_id: int | None = None


class AdminTaskCreateRequest(BaseModel):
    """관리자용 간편 태스크 생성 — 날짜 미입력 시 프로젝트/오늘 기준."""

    title: str = Field(min_length=1, max_length=200)
    assignee_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: str = "TODO"

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        from app.models.task import TaskStatus

        if v not in TaskStatus.ALL:
            raise ValueError(f"status는 {sorted(TaskStatus.ALL)} 중 하나여야 합니다.")
        return v


class AdminMaterialDetailResponse(ArchiveDocResponse):
    versions: list[DocVersionResponse] = []


class AdminAuditLogResponse(ORMModel):
    id: int
    admin_id: int
    admin_login_id: str
    action: str
    target_type: str
    target_id: int | None
    target_label: str
    detail: str | None
    created_at: datetime
