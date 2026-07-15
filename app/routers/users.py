from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import token_store
from app.core.deps import get_current_user
from app.core.errors import ErrorCode, bad_request, conflict
from app.core.pagination import DEFAULT_SIZE, MAX_SIZE, paginate, parse_page_params
from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.models import LoginHistory, Payment, Project, Task, User
from app.models.payment import PaymentMethod
from app.models.task import TaskStatus, task_assignee
from app.models.user import UserPlan
from app.schemas.common import PageResponse
from app.schemas.my_work import MyTaskItem
from app.schemas.payment import PaymentResponse
from app.schemas.user import (
    LoginHistoryResponse,
    PasswordChangeRequest,
    PlanUpdateRequest,
    UserResponse,
    UserUpdateRequest,
)
from app.services.payment_service import apply_plan_change
from app.services.user_service import apply_lazy_plan_expiry, withdraw_user

router = APIRouter(prefix="/api/users", tags=["User"])


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


@router.get("/me/login-history", response_model=PageResponse[LoginHistoryResponse])
def list_login_history(
    page: int = Query(1),
    size: int = Query(DEFAULT_SIZE),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """본인 로그인 이력 — 성공/실패 포함 최신순."""
    if page < 1 or size < 1 or size > MAX_SIZE:
        raise bad_request(message=f"page는 1 이상, size는 1~{MAX_SIZE} 사이여야 합니다.")
    filters = [LoginHistory.user_id == user.id]
    total = db.scalar(select(func.count()).select_from(LoginHistory).where(*filters)) or 0
    items = list(
        db.scalars(
            select(LoginHistory)
            .where(*filters)
            .order_by(LoginHistory.created_at.desc(), LoginHistory.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
    )
    return {
        "items": items,
        "page": page,
        "size": size,
        "total_elements": total,
        "total_pages": (total + size - 1) // size,
    }


@router.put("/me/plan", response_model=UserResponse)
def update_plan(body: PlanUpdateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.plan not in (UserPlan.FREE, UserPlan.PRO):
        raise bad_request(ErrorCode.INVALID_PLAN, f"유효하지 않은 요금제입니다: {body.plan}")
    apply_plan_change(
        db,
        user,
        next_plan=body.plan,
        method=PaymentMethod.CARD_MOCK,
        payer_name=body.payer_name,
        payer_email=str(body.payer_email) if body.payer_email else None,
    )
    db.commit()
    db.refresh(user)
    return user


@router.get("/me/payments", response_model=PageResponse[PaymentResponse])
def list_my_payments(
    page: int = Query(1),
    size: int = Query(DEFAULT_SIZE),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    params = parse_page_params(page, size, "created_at,desc", {"created_at"})
    stmt = select(Payment).where(Payment.user_id == user.id)
    return paginate(db, stmt, Payment, params)


@router.get("/me/tasks", response_model=list[MyTaskItem])
def list_my_tasks(
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """내가 담당자로 지정된 프로젝트 Task 목록 (마감일 가까운 순)."""
    if status is not None and status not in TaskStatus.ALL:
        raise bad_request(message=f"status 필터는 {sorted(TaskStatus.ALL)} 중 하나여야 합니다.")

    stmt = (
        select(Task, Project.name)
        .join(task_assignee, task_assignee.c.task_id == Task.id)
        .join(Project, Project.id == Task.project_id)
        .where(task_assignee.c.user_id == user.id)
        .order_by(Task.end_date.asc(), Task.id.asc())
        .limit(limit)
    )
    if status is not None:
        stmt = stmt.where(Task.status == status)

    rows = db.execute(stmt).all()
    return [
        MyTaskItem(
            id=task.id,
            project_id=task.project_id,
            project_title=project_name,
            title=task.title,
            status=task.status,
            start_date=task.start_date,
            end_date=task.end_date,
            color=task.color,
        )
        for task, project_name in rows
    ]


@router.delete("/me", status_code=204)
def delete_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    withdraw_user(db, user)
