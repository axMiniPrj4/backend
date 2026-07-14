"""회원 탈퇴 공통 로직 — 본인 탈퇴(DELETE /users/me)와 관리자 삭제(기준안 #3)가 공유."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import token_store
from app.core.errors import ErrorCode, conflict
from app.db.base import utcnow
from app.models import ProjectMember, User
from app.models.project import MemberRole
from app.models.user import UserPlan


def apply_lazy_plan_expiry(db: Session, user: User) -> None:
    """기준안 #9: 로그인·내 정보 조회 시점에 PRO 만료 확인 후 FREE로 lazy 전환."""
    if user.plan == UserPlan.PRO and user.plan_expires_at is not None and user.plan_expires_at <= utcnow():
        user.plan = UserPlan.FREE
        user.plan_expires_at = None
        db.commit()


def withdraw_user(db: Session, user: User) -> None:
    """user soft delete + login_id/email/nickname 변형 + Redis RT 삭제 (단일 트랜잭션).

    LEADER인 프로젝트가 하나라도 있으면 409 — 위임/삭제 후 가능.
    """
    leader_exists = db.scalar(
        select(ProjectMember.id)
        .where(ProjectMember.user_id == user.id, ProjectMember.role == MemberRole.LEADER)
        .limit(1)
    )
    if leader_exists:
        raise conflict(ErrorCode.LEADER_PROJECT_EXISTS, "팀장(LEADER)인 프로젝트가 있어 탈퇴할 수 없습니다. 위임 또는 삭제 후 다시 시도하세요.")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    prefix = f"del_{ts}_"
    user.login_id = f"{prefix}{user.login_id}"[:100]
    user.email = f"{prefix}{user.email}"[:255]
    user.nickname = f"{prefix}{user.nickname}"[:100]
    user.soft_delete()
    db.commit()
    token_store.delete_refresh_token(user.id)
