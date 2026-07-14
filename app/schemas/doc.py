from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class DocUpdateRequest(BaseModel):
    """게시글 수정은 title/content만 (JSON). 파일 변경은 새 버전 업로드로."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = None


class DocVersionResponse(ORMModel):
    id: int
    version_no: int
    file_name: str
    file_size: int
    mime_type: str
    uploaded_by: int
    created_at: datetime


class DocResponse(BaseModel):
    id: int
    project_id: int | None  # NULL = 공통 자료
    user_id: int
    title: str
    content: str | None
    created_at: datetime
    updated_at: datetime
    latest_version: DocVersionResponse | None


class ArchiveDocResponse(DocResponse):
    """전역 자료실 목록/상세용 — 소속 프로젝트 이름 포함 (공통 자료는 NULL)."""

    project_name: str | None = None
    author_nickname: str
