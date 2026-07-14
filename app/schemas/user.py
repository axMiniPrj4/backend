import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel

# 기준안 #5: 비밀번호 8~64자, 영문+숫자 포함
_PW_LETTER = re.compile(r"[A-Za-z]")
_PW_DIGIT = re.compile(r"\d")


def validate_password(v: str) -> str:
    if not (8 <= len(v) <= 64) or not _PW_LETTER.search(v) or not _PW_DIGIT.search(v):
        raise ValueError("비밀번호는 8~64자이며 영문과 숫자를 포함해야 합니다.")
    return v


class SignupRequest(BaseModel):
    login_id: str = Field(min_length=4, max_length=30)
    password: str
    name: str = Field(min_length=1, max_length=50)
    nickname: str = Field(min_length=1, max_length=30)
    email: EmailStr

    _pw = field_validator("password")(validate_password)


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
    """기준안 #2: 닉네임·이메일·비밀번호만 수정 가능."""

    nickname: str | None = Field(default=None, min_length=1, max_length=30)
    email: EmailStr | None = None
    password: str | None = None

    @field_validator("password")
    @classmethod
    def _pw(cls, v):
        return validate_password(v) if v is not None else v


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
