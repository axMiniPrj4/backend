import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel

# 기준안 #5 (2026-07-14 개정): 비밀번호 8~16자, 영문+숫자+특수문자 포함 — 프론트 정책과 통일
_PW_LETTER = re.compile(r"[A-Za-z]")
_PW_DIGIT = re.compile(r"\d")
_PW_SPECIAL = re.compile(r"[^A-Za-z0-9]")


def validate_password(v: str) -> str:
    if (
        not (8 <= len(v) <= 16)
        or not _PW_LETTER.search(v)
        or not _PW_DIGIT.search(v)
        or not _PW_SPECIAL.search(v)
    ):
        raise ValueError("비밀번호는 8~16자이며 영문, 숫자, 특수문자를 모두 포함해야 합니다.")
    return v


class SignupRequest(BaseModel):
    login_id: str = Field(min_length=4, max_length=30)
    password: str
    name: str = Field(min_length=1, max_length=50)
    nickname: str = Field(min_length=1, max_length=30)
    email: EmailStr
    # 필수 동의 — 프론트 가입 폼의 단일 체크박스(이용약관+개인정보 처리방침)와 대응. false면 가입 불가 (400)
    legal_agreed: bool

    _pw = field_validator("password")(validate_password)

    @field_validator("legal_agreed")
    @classmethod
    def _legal(cls, v):
        if not v:
            raise ValueError("이용약관 및 개인정보 처리방침에 동의해야 가입할 수 있습니다.")
        return v


class LoginRequest(BaseModel):
    login_id: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"


class UserUpdateRequest(BaseModel):
    """기준안 #2: 닉네임·이메일만 수정 가능. 비밀번호는 전용 API(POST /users/me/password)로 분리."""

    nickname: str | None = Field(default=None, min_length=1, max_length=30)
    email: EmailStr | None = None


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

    _pw = field_validator("new_password")(validate_password)


class PlanUpdateRequest(BaseModel):
    plan: str


class UserResponse(ORMModel):
    id: int
    login_id: str
    name: str
    nickname: str
    email: str
    role: str
    plan: str
    plan_expires_at: datetime | None
    created_at: datetime


class AvailabilityResponse(BaseModel):
    available: bool


class LoginHistoryResponse(ORMModel):
    id: int
    ip: str | None
    user_agent: str | None
    success: bool
    created_at: datetime


class FindLoginIdRequest(BaseModel):
    email: EmailStr


class FindLoginIdResponse(BaseModel):
    login_id: str


class ResetPasswordRequest(BaseModel):
    login_id: str
    email: EmailStr
    new_password: str

    _pw = field_validator("new_password")(validate_password)
