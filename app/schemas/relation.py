from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class RelatedDocOut(BaseModel):
    id: int
    title: str
    latest_file_name: str | None = None
    version_no: int | None = None
    relation_types: list[str] = Field(default_factory=list)


class RelatedTaskOut(BaseModel):
    id: int
    title: str
    status: str


class MatchingOprRowOut(BaseModel):
    row_id: int
    section_type: str
    content: str


class RelatedOprOut(BaseModel):
    report_id: int
    report_date: date
    author_id: int
    author_nickname: str
    author_name: str | None = None
    status: str
    matching_rows: list[MatchingOprRowOut] = Field(default_factory=list)


class TaskRelationsOut(BaseModel):
    task: RelatedTaskOut
    opr_reports: list[RelatedOprOut]
    documents: list[RelatedDocOut]


class OprRelationsOut(BaseModel):
    report_id: int
    tasks: list[RelatedTaskOut]
    documents: list[RelatedDocOut]


class DocRelationsOut(BaseModel):
    doc_id: int
    tasks: list[RelatedTaskOut]
    opr_reports: list[RelatedOprOut]


class RelationLinkOut(ORMModel):
    project_id: int
    linked_by: int
    created_at: datetime
