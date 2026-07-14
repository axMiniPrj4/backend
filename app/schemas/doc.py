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
    project_id: int
    user_id: int
    title: str
    content: str | None
    created_at: datetime
    updated_at: datetime
    latest_version: DocVersionResponse | None
