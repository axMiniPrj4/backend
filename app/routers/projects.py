from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import ProjectContext, get_current_user, get_project_context, require_leader
from app.core.errors import ErrorCode, bad_request, conflict, not_found
from app.core.pagination import DEFAULT_SIZE, parse_page_params, paginate
from app.db.session import get_db
from app.models import Project, ProjectMember, User
from app.models.project import MemberRole
from app.schemas.common import PageResponse
from app.schemas.project import (
    ProjectCodeResponse,
    ProjectCreateRequest,
    ProjectJoinRequest,
    ProjectListItemResponse,
    ProjectResponse,
    ProjectUpdateRequest,
)
from app.services.project_service import cascade_delete_project, generate_unique_code

router = APIRouter(prefix="/api/projects", tags=["Project"])

_SORT_FIELDS = {"created_at", "name", "priority", "status", "start_date", "end_date"}


def _validate_dates(start, end):
    if start is not None and end is not None and start > end:
        raise bad_request(ErrorCode.INVALID_DATE_RANGE, "시작일은 종료일보다 늦을 수 없습니다.")


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(body: ProjectCreateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _validate_dates(body.start_date, body.end_date)
    # 단일 트랜잭션: project INSERT + 코드 발급 + LEADER 등록
    project = Project(
        name=body.name,
        description=body.description,
        priority=body.priority,
        status=body.status,
        start_date=body.start_date,
        end_date=body.end_date,
        code=generate_unique_code(db),
    )
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role=MemberRole.LEADER))
    db.commit()
    return project


@router.get("", response_model=PageResponse[ProjectListItemResponse])
def list_my_projects(
    page: int = Query(1),
    size: int = Query(DEFAULT_SIZE),
    sort: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    params = parse_page_params(page, size, sort, _SORT_FIELDS)
    stmt = (
        select(Project)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.user_id == user.id)
    )
    return paginate(db, stmt, Project, params)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(ctx: ProjectContext = Depends(get_project_context)):
    return ctx.project


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(body: ProjectUpdateRequest, ctx: ProjectContext = Depends(require_leader), db: Session = Depends(get_db)):
    project = ctx.project
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(project, field, value)
    _validate_dates(project.start_date, project.end_date)
    db.commit()
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(ctx: ProjectContext = Depends(require_leader), db: Session = Depends(get_db)):
    cascade_delete_project(db, ctx.project)


@router.post("/join", response_model=ProjectResponse, status_code=201)
def join_project(body: ProjectJoinRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.scalar(select(Project).where(Project.code == body.code))
    if project is None:
        raise not_found("유효하지 않은 참여 코드입니다.", ErrorCode.INVALID_PROJECT_CODE)
    already = db.scalar(
        select(ProjectMember.id).where(
            ProjectMember.project_id == project.id, ProjectMember.user_id == user.id
        )
    )
    if already:
        raise conflict(ErrorCode.ALREADY_JOINED, "이미 참여 중인 프로젝트입니다.")
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role=MemberRole.MEMBER))
    db.commit()
    return project


@router.post("/{project_id}/code", response_model=ProjectCodeResponse)
def regenerate_code(ctx: ProjectContext = Depends(require_leader), db: Session = Depends(get_db)):
    # 기존 코드 즉시 무효 (교체)
    ctx.project.code = generate_unique_code(db)
    db.commit()
    return ProjectCodeResponse(code=ctx.project.code)
