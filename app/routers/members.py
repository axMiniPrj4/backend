from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import ProjectContext, get_project_context, require_leader
from app.core.errors import ErrorCode, bad_request, conflict, not_found
from app.db.session import get_db
from app.models import ProjectMember
from app.models.project import MemberRole
from app.schemas.project import LeaderDelegateRequest, MemberResponse

router = APIRouter(prefix="/api/projects/{project_id}", tags=["Member"])


@router.get("/members", response_model=list[MemberResponse])
def list_members(ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    members = db.scalars(
        select(ProjectMember)
        .where(ProjectMember.project_id == ctx.project.id)
        .options(selectinload(ProjectMember.user))
        .order_by(ProjectMember.joined_at.asc(), ProjectMember.id.asc())
    ).all()
    return [
        MemberResponse(
            user_id=m.user_id, name=m.user.name, nickname=m.user.nickname, role=m.role, joined_at=m.joined_at
        )
        for m in members
    ]


@router.delete("/members/me", status_code=204)
def leave_project(ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    if ctx.is_leader:
        raise conflict(ErrorCode.LEADER_CANNOT_LEAVE, "팀장은 위임 후에만 탈퇴할 수 있습니다.")
    db.delete(ctx.member)  # Hard Delete — 재참여 시 신규 행
    db.commit()


@router.delete("/members/{user_id}", status_code=204)
def kick_member(user_id: int, ctx: ProjectContext = Depends(require_leader), db: Session = Depends(get_db)):
    if user_id == ctx.user.id:
        raise bad_request(message="자기 자신은 강퇴할 수 없습니다. 탈퇴 또는 위임을 사용하세요.")
    target = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == ctx.project.id, ProjectMember.user_id == user_id
        )
    )
    if target is None:
        raise not_found("해당 멤버를 찾을 수 없습니다.")
    db.delete(target)  # Hard Delete
    db.commit()


@router.put("/leader", response_model=list[MemberResponse])
def delegate_leader(
    body: LeaderDelegateRequest,
    ctx: ProjectContext = Depends(require_leader),
    db: Session = Depends(get_db),
):
    # 멱등: 대상이 이미 LEADER(=본인)면 변경 없이 성공
    if body.user_id != ctx.user.id:
        target = db.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == ctx.project.id, ProjectMember.user_id == body.user_id
            )
        )
        if target is None:
            raise not_found("해당 멤버를 찾을 수 없습니다.")
        # 단일 트랜잭션: 대상 MEMBER→LEADER + 기존 LEADER→MEMBER (LEADER 1명 불변식)
        target.role = MemberRole.LEADER
        ctx.member.role = MemberRole.MEMBER
        db.commit()
    return list_members(ctx, db)
