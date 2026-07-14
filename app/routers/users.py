from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import token_store
from app.core.deps import get_current_user
from app.core.errors import ErrorCode, bad_request, conflict
from app.core.security import hash_password, verify_password
from app.db.base import utcnow
from app.db.session import get_db
from app.models import User
from app.models.user import UserPlan
from app.schemas.user import PasswordChangeRequest, PlanUpdateRequest, UserResponse, UserUpdateRequest
from app.services.user_service import apply_lazy_plan_expiry, withdraw_user

router = APIRouter(prefix="/api/users", tags=["User"])

PRO_DURATION_DAYS = 30  # 기준안 #8: PRO 전환 시점 + 30일


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    apply_lazy_plan_expiry(db, user)
    return user


@router.patch("/me", response_model=UserResponse)
def update_me(body: UserUpdateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.nickname is not None and body.nickname != user.nickname:
        if db.scalar(select(User.id).where(User.nickname == body.nickname).execution_options(include_deleted=True)):
            raise conflict(ErrorCode.DUPLICATE_NICKNAME, "이미 사용 중인 닉네임입니다.")
        user.nickname = body.nickname
    if body.email is not None and body.email != user.email:
        if db.scalar(select(User.id).where(User.email == body.email).execution_options(include_deleted=True)):
            raise conflict(ErrorCode.DUPLICATE_EMAIL, "이미 사용 중인 이메일입니다.")
        user.email = body.email
    db.commit()
    return user


@router.post("/me/password", status_code=204)
def change_password(body: PasswordChangeRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise bad_request(ErrorCode.INVALID_CREDENTIALS, "현재 비밀번호가 올바르지 않습니다.")
    if body.new_password == body.current_password:
        raise bad_request(ErrorCode.VALIDATION_ERROR, "새 비밀번호가 현재 비밀번호와 같습니다.")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    # 다른 기기 세션 차단 — RT 폐기 (보유한 AT는 만료까지 유효)
    token_store.delete_refresh_token(user.id)


@router.put("/me/plan", response_model=UserResponse)
def update_plan(body: PlanUpdateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.plan not in (UserPlan.FREE, UserPlan.PRO):
        raise bad_request(ErrorCode.INVALID_PLAN, f"유효하지 않은 요금제입니다: {body.plan}")
    if body.plan == UserPlan.PRO:
        # PRO 재호출 = 재구독 (만료일 갱신)
        user.plan = UserPlan.PRO
        user.plan_expires_at = utcnow() + timedelta(days=PRO_DURATION_DAYS)
    else:
        # FREE 전환 = 즉시 해지
        user.plan = UserPlan.FREE
        user.plan_expires_at = None
    db.commit()
    return user


@router.delete("/me", status_code=204)
def delete_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    withdraw_user(db, user)
