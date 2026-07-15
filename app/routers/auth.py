from secrets import token_urlsafe

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import token_store
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.errors import ErrorCode, bad_request, conflict, not_found, unauthorized
from app.core.security import (
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.base import utcnow
from app.db.session import get_db
from app.models import LoginHistory, User
from app.schemas.user import (
    AvailabilityResponse,
    FindLoginIdRequest,
    FindLoginIdResponse,
    LoginRequest,
    RefreshRequest,
    ResetPasswordConfirmRequest,
    ResetPasswordMailRequest,
    ResetPasswordMailResponse,
    ResetPasswordRequest,
    SignupRequest,
    TokenResponse,
    UserResponse,
)
from app.services import mail as mail_service
from app.services.user_service import apply_lazy_plan_expiry

router = APIRouter(prefix="/api/auth", tags=["Auth"])


def _check_duplicates(db: Session, login_id: str | None = None, email: str | None = None, nickname: str | None = None):
    """중복 3종 검사 — Soft Delete 계정은 값이 변형 저장되므로 원본 값 재사용 가능."""
    if login_id and db.scalar(select(User.id).where(User.login_id == login_id).execution_options(include_deleted=True)):
        raise conflict(ErrorCode.DUPLICATE_LOGIN_ID, "이미 사용 중인 아이디입니다.")
    if email and db.scalar(select(User.id).where(User.email == email).execution_options(include_deleted=True)):
        raise conflict(ErrorCode.DUPLICATE_EMAIL, "이미 사용 중인 이메일입니다.")
    if nickname and db.scalar(select(User.id).where(User.nickname == nickname).execution_options(include_deleted=True)):
        raise conflict(ErrorCode.DUPLICATE_NICKNAME, "이미 사용 중인 닉네임입니다.")


@router.post("/signup", response_model=UserResponse, status_code=201)
def signup(body: SignupRequest, db: Session = Depends(get_db)):
    _check_duplicates(db, body.login_id, body.email, body.nickname)
    now = utcnow()  # 필수 동의 시각 기록 (스키마에서 미동의는 400 처리됨)
    user = User(
        login_id=body.login_id,
        password_hash=hash_password(body.password),
        name=body.name,
        nickname=body.nickname,
        email=body.email,
        terms_agreed_at=now,
        privacy_agreed_at=now,
    )
    db.add(user)
    db.commit()
    return user


def _record_login(db: Session, request: Request, user_id: int, success: bool):
    """로그인 시도 적재 — 프록시 경유 시 X-Forwarded-For 첫 IP가 실제 클라이언트.
    이력 테이블 부재/DB 오류는 로그인 자체를 막지 않도록 soft-fail."""
    xff = request.headers.get("X-Forwarded-For")
    ip = xff.split(",")[0].strip() if xff else (request.client.host if request.client else None)
    user_agent = (request.headers.get("User-Agent") or "")[:255] or None
    try:
        db.add(LoginHistory(user_id=user_id, ip=ip, user_agent=user_agent, success=success))
        db.commit()
    except Exception:
        db.rollback()


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.login_id == body.login_id))
    # 계정 존재 여부 비노출 — 아이디/비밀번호 오류 모두 동일 401
    if user is None or not verify_password(body.password, user.password_hash):
        if user is not None:  # 미존재 아이디는 적재 대상 아님 (LoginHistory docstring 참고)
            _record_login(db, request, user.id, success=False)
        raise unauthorized(ErrorCode.INVALID_CREDENTIALS, "아이디 또는 비밀번호가 올바르지 않습니다.")
    if getattr(user, "is_suspended", False):
        _record_login(db, request, user.id, success=False)
        raise unauthorized(ErrorCode.INVALID_CREDENTIALS, "정지된 계정입니다. 관리자에게 문의하세요.")
    _record_login(db, request, user.id, success=True)
    apply_lazy_plan_expiry(db, user)
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    token_store.save_refresh_token(user.id, refresh_token)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout", status_code=204)
def logout(user: User = Depends(get_current_user)):
    token_store.delete_refresh_token(user.id)


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest):
    user_id = decode_token(body.refresh_token, TOKEN_TYPE_REFRESH)
    stored = token_store.get_refresh_token(user_id)
    # 기준안 #1: RT 미회전 — 저장된 RT와 일치할 때만 AT 재발급
    if stored is None or stored != body.refresh_token:
        raise unauthorized(ErrorCode.INVALID_TOKEN, "유효하지 않은 토큰입니다.")
    return TokenResponse(access_token=create_access_token(user_id), refresh_token=body.refresh_token)


@router.get("/check-login-id", response_model=AvailabilityResponse)
def check_login_id(login_id: str = Query(min_length=1), db: Session = Depends(get_db)):
    exists = db.scalar(select(User.id).where(User.login_id == login_id).execution_options(include_deleted=True))
    return AvailabilityResponse(available=exists is None)


@router.get("/check-email", response_model=AvailabilityResponse)
def check_email(email: str = Query(min_length=1), db: Session = Depends(get_db)):
    exists = db.scalar(select(User.id).where(User.email == email).execution_options(include_deleted=True))
    return AvailabilityResponse(available=exists is None)


@router.get("/check-nickname", response_model=AvailabilityResponse)
def check_nickname(nickname: str = Query(min_length=1), db: Session = Depends(get_db)):
    exists = db.scalar(select(User.id).where(User.nickname == nickname).execution_options(include_deleted=True))
    return AvailabilityResponse(available=exists is None)


@router.post("/find-login-id", response_model=FindLoginIdResponse)
def find_login_id(body: FindLoginIdRequest, db: Session = Depends(get_db)):
    """이메일이 일치하면 아이디를 화면에 반환. (메일 발송은 SMTP 설정 시에만 시도)"""
    user = db.scalar(select(User).where(User.email == body.email))
    if user is None:
        raise not_found("해당 이메일로 가입된 계정을 찾을 수 없습니다.")
    email_sent = False
    if settings.mail_enabled:
        email_sent = mail_service.send_find_login_id_email(to=user.email, login_id=user.login_id)
    return FindLoginIdResponse(login_id=user.login_id, email_sent=email_sent)


@router.post("/reset-password", status_code=204)
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    """아이디+이메일이 일치하면 새 비밀번호로 즉시 변경. (메일 연동 없이 사용 가능)"""
    user = db.scalar(
        select(User).where(User.login_id == body.login_id, User.email == body.email)
    )
    if user is None:
        raise not_found("아이디와 이메일이 일치하는 계정을 찾을 수 없습니다.")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    token_store.delete_refresh_token(user.id)
    if settings.mail_enabled:
        mail_service.send_password_changed_email(to=user.email)


@router.post("/reset-password/request", response_model=ResetPasswordMailResponse)
def request_password_reset(body: ResetPasswordMailRequest, db: Session = Depends(get_db)):
    """이메일로 재설정 링크 발송. SMTP 미설정 시 MAIL_NOT_CONFIGURED → FE가 즉시 재설정 폼으로 폴백."""
    if not settings.mail_enabled:
        raise bad_request(
            ErrorCode.MAIL_NOT_CONFIGURED,
            "메일 서버가 설정되지 않았습니다. 화면에서 바로 새 비밀번호를 설정해 주세요.",
        )

    user = db.scalar(
        select(User).where(User.login_id == body.login_id, User.email == body.email)
    )
    if user is None:
        raise not_found("아이디와 이메일이 일치하는 계정을 찾을 수 없습니다.")

    token = token_urlsafe(32)
    token_store.save_password_reset_token(token, user.id)
    minutes = settings.password_reset_token_minutes
    base = settings.frontend_base_url.rstrip("/")
    reset_url = f"{base}/reset-password/confirm?token={token}"
    sent = mail_service.send_password_reset_email(
        to=user.email, reset_url=reset_url, minutes=minutes
    )
    if not sent:
        raise bad_request(
            ErrorCode.MAIL_NOT_CONFIGURED,
            "메일 발송에 실패했습니다. 잠시 후 다시 시도하거나 화면에서 바로 재설정해 주세요.",
        )
    return ResetPasswordMailResponse(email_sent=True, expires_minutes=minutes)


@router.post("/reset-password/confirm", status_code=204)
def confirm_password_reset(body: ResetPasswordConfirmRequest, db: Session = Depends(get_db)):
    """(선택) 메일 링크 방식 — SMTP 연동 후 사용."""
    user_id = token_store.pop_password_reset_token(body.token.strip())
    if user_id is None:
        raise bad_request(ErrorCode.INVALID_TOKEN, "재설정 링크가 만료되었거나 올바르지 않습니다.")
    user = db.get(User, user_id)
    if user is None:
        raise not_found("사용자를 찾을 수 없습니다.")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    token_store.delete_refresh_token(user.id)
    if settings.mail_enabled:
        mail_service.send_password_changed_email(to=user.email)
