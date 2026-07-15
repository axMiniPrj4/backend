from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class DocUpdateRequest(BaseModel):
    """자료 수정 — title/content/project_id(JSON). 파일 변경은 새 버전 업로드로."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = None
    # 명시적으로 null 보내면 공통 자료로 이동. 미전송 시 소속 유지.
    project_id: int | None = None


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
