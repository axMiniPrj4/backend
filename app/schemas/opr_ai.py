from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.opr_ai import AiProvider
from app.schemas.common import ORMModel

# 입력 길이 상한 — opr_row.content(5000) 와 같은 기준
_LONG_TEXT = 5000


class OprAiProviderInput(BaseModel):
    provider: str = Field(max_length=30)
    custom_provider_name: str = Field(default="", max_length=100)

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        normalized = (value or "").strip().upper()
        if normalized not in AiProvider.ALL:
            raise ValueError(f"provider는 {sorted(AiProvider.ALL)} 중 하나여야 합니다.")
        return normalized

    @field_validator("custom_provider_name")
    @classmethod
    def normalize_custom(cls, value: str | None) -> str:
        return " ".join((value or "").split())

    @model_validator(mode="after")
    def check_other(self):
        if self.provider == AiProvider.OTHER:
            if not self.custom_provider_name:
                raise ValueError("'기타'를 선택하면 AI 이름을 입력해야 합니다.")
        else:
            # 기타가 아니면 직접 입력 이름은 저장하지 않는다 (중복 판정 기준을 단순하게 유지)
            self.custom_provider_name = ""
        return self


class OprAiRecordInput(BaseModel):
    """AI 기록 입력.

    id 가 있으면 기존 기록 갱신, 없으면 새로 생성한다.
    (OPR 저장이 문서 통째 저장 방식이라 id 기준 upsert 가 필요하다)
    """

    id: int | None = None
    title: str = Field(max_length=200)
    question: str = Field(max_length=_LONG_TEXT)
    answer_summary: str | None = Field(default=None, max_length=_LONG_TEXT)
    application_result: str = Field(max_length=_LONG_TEXT)
    lesson_learned: str | None = Field(default=None, max_length=_LONG_TEXT)
    artifact_link: str | None = Field(default=None, max_length=1000)
    sort_order: int = Field(default=0, ge=0)
    providers: list[OprAiProviderInput] = Field(min_length=1, max_length=20)
    task_ids: list[int] = Field(default_factory=list, max_length=50)
    doc_ids: list[int] = Field(default_factory=list, max_length=50)

    @field_validator("title", "question", "application_result")
    @classmethod
    def required_not_blank(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("필수 항목은 공백만으로 채울 수 없습니다.")
        return cleaned

    @field_validator("answer_summary", "lesson_learned", "artifact_link")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def dedupe(self):
        seen: set[tuple[str, str]] = set()
        for item in self.providers:
            key = (item.provider, item.custom_provider_name.casefold())
            if key in seen:
                raise ValueError("같은 AI를 중복해서 선택할 수 없습니다.")
            seen.add(key)
        # 연결 id 는 순서를 유지하며 중복만 제거한다
        self.task_ids = list(dict.fromkeys(self.task_ids))
        self.doc_ids = list(dict.fromkeys(self.doc_ids))
        return self


class OprAiProviderResponse(ORMModel):
    provider: str
    custom_provider_name: str


class OprAiRecordResponse(ORMModel):
    id: int
    report_id: int
    author_id: int
    title: str
    question: str
    answer_summary: str | None
    application_result: str
    lesson_learned: str | None
    artifact_link: str | None
    sort_order: int
    providers: list[OprAiProviderResponse]
    task_ids: list[int]
    doc_ids: list[int]
    created_at: datetime
    updated_at: datetime


class OprAiRecordUpdate(BaseModel):
    """PATCH 용. 보낸 필드만 바꾼다."""

    title: str | None = Field(default=None, max_length=200)
    question: str | None = Field(default=None, max_length=_LONG_TEXT)
    answer_summary: str | None = Field(default=None, max_length=_LONG_TEXT)
    application_result: str | None = Field(default=None, max_length=_LONG_TEXT)
    lesson_learned: str | None = Field(default=None, max_length=_LONG_TEXT)
    artifact_link: str | None = Field(default=None, max_length=1000)
    sort_order: int | None = Field(default=None, ge=0)
    providers: list[OprAiProviderInput] | None = Field(default=None, max_length=20)
    task_ids: list[int] | None = Field(default=None, max_length=50)
    doc_ids: list[int] | None = Field(default=None, max_length=50)

    @field_validator("title", "question", "application_result")
    @classmethod
    def required_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("필수 항목은 공백만으로 채울 수 없습니다.")
        return cleaned

    @field_validator("answer_summary", "lesson_learned", "artifact_link")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def dedupe(self):
        if self.providers is not None:
            if not self.providers:
                raise ValueError("사용한 AI를 최소 하나 선택해야 합니다.")
            seen: set[tuple[str, str]] = set()
            for item in self.providers:
                key = (item.provider, item.custom_provider_name.casefold())
                if key in seen:
                    raise ValueError("같은 AI를 중복해서 선택할 수 없습니다.")
                seen.add(key)
        if self.task_ids is not None:
            self.task_ids = list(dict.fromkeys(self.task_ids))
        if self.doc_ids is not None:
            self.doc_ids = list(dict.fromkeys(self.doc_ids))
        return self
