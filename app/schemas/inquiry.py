from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class InquiryUpdateRequest(BaseModel):
    """WAITING 상태에서만 수정 가능. 첨부 교체는 미지원(명세 범위 외)."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = None


class AnswerCreateRequest(BaseModel):
    content: str = Field(min_length=1)


class AnswerResponse(ORMModel):
    id: int
    question_id: int
    user_id: int
    content: str
    created_at: datetime


class InquiryResponse(ORMModel):
    id: int
    user_id: int
    project_id: int | None
    title: str
    content: str
    status: str
    file_name: str | None
    file_size: int | None
    mime_type: str | None
    created_at: datetime
    updated_at: datetime
    answer: AnswerResponse | None = None
