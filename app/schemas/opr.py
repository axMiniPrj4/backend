from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.models.opr import OprReportStatus, OprSection
from app.schemas.common import ORMModel


class OprRowInput(BaseModel):
    section_type: str
    content: str = Field(min_length=1, max_length=5000)
    status: str | None = Field(default=None, max_length=30)
    assignee_name: str | None = Field(default=None, max_length=300)
    planned_date: date | None = None
    completed_date: date | None = None
    artifact_link: str | None = Field(default=None, max_length=1000)
    issue_request: str | None = Field(default=None, max_length=5000)
    task_id: int | None = None
    doc_id: int | None = None
    source: str = Field(default="MANUAL", max_length=20)
    sort_order: int = Field(default=0, ge=0)

    @field_validator("section_type")
    @classmethod
    def validate_section(cls, value: str) -> str:
        if value not in OprSection.ALL:
            raise ValueError(f"section_type은 {sorted(OprSection.ALL)} 중 하나여야 합니다.")
        return value


class OprReportSaveRequest(BaseModel):
    status: str = OprReportStatus.DRAFT
    rows: list[OprRowInput] = Field(default_factory=list, max_length=500)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in OprReportStatus.ALL:
            raise ValueError(f"status는 {sorted(OprReportStatus.ALL)} 중 하나여야 합니다.")
        return value


class OprRowResponse(ORMModel):
    id: int
    section_type: str
    content: str
    status: str | None
    assignee_name: str | None
    planned_date: date | None
    completed_date: date | None
    artifact_link: str | None
    issue_request: str | None
    task_id: int | None
    doc_id: int | None
    source: str
    sort_order: int


class OprReportResponse(ORMModel):
    id: int
    project_id: int
    report_date: date
    status: str
    author_id: int
    author_nickname: str
    rows: list[OprRowResponse]
    created_at: datetime
    updated_at: datetime


class OprSourceResponse(BaseModel):
    project_id: int
    report_date: date
    rows: list[OprRowInput]
