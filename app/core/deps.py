"""권한 체크 4단계 Depends 체인 — ① JWT(401) ② 역할(403) ③ 프로젝트 멤버십(403) ④ 리소스 소유권(각 라우터)."""
from dataclasses import dataclass

from fastapi import Depends, Path, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode, forbidden, not_found, unauthorized
from app.core.security import TOKEN_TYPE_ACCESS, decode_token
from app.db.session import get_db
from app.models import Project, ProjectMember, User
from app.models.project import CollabPermission, MemberRole
from app.models.user import UserRole

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
    db: Session = Depends(get_db),
) -> User:
    # ① JWT 검증
    if credentials is None:
        raise unauthorized(ErrorCode.INVALID_TOKEN, "인증 토큰이 필요합니다.")
    user_id = decode_token(credentials.credentials, TOKEN_TYPE_ACCESS)
    user = db.get(User, user_id)
    if user is None or user.is_deleted:
        raise unauthorized(ErrorCode.INVALID_TOKEN, "유효하지 않은 토큰입니다.")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    # ② 역할 검증
    if user.role != UserRole.SYSTEM_ADMIN:
        raise forbidden("관리자 권한이 필요합니다.")
    return user


@dataclass
class ProjectContext:
    project: Project
    member: ProjectMember
    user: User

    @property
    def is_leader(self) -> bool:
        return self.member.role == MemberRole.LEADER

    @property
    def is_editor(self) -> bool:
        # 팀장은 뷰어로 지정되어 있어도 항상 편집 가능
        return self.is_leader or self.member.collab_permission != CollabPermission.VIEWER


def get_project_context(
    project_id: int = Path(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectContext:
    # ③ 프로젝트 존재(404) + 멤버십(403)
    project = db.get(Project, project_id)
    if project is None or project.is_deleted:
        raise not_found("프로젝트를 찾을 수 없습니다.")
    member = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user.id
        )
    )
    if member is None:
        raise forbidden("프로젝트 멤버가 아닙니다.")
    return ProjectContext(project=project, member=member, user=user)


def require_leader(ctx: ProjectContext = Depends(get_project_context)) -> ProjectContext:
    if not ctx.is_leader:
        raise forbidden("팀장(LEADER) 권한이 필요합니다.")
    return ctx


def require_editor(ctx: ProjectContext = Depends(get_project_context)) -> ProjectContext:
    if not ctx.is_editor:
        raise forbidden("보기 권한만 있어 편집할 수 없습니다.")
    return ctx
