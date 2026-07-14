from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import require_admin
from app.core.errors import ErrorCode, bad_request, conflict, forbidden, not_found
from app.core.files import stream_download
from app.core.pagination import DEFAULT_SIZE, parse_page_params, paginate
from app.core.security import hash_password
from app.db.session import get_db
from app.models import AnswerTemplate, Doc, DocVersion, Inquiry, LoginHistory, Notice, Payment, Project, ProjectMember, Task, User
from app.models.admin_audit_log import AdminAuditLog
from app.models.inquiry import InquiryStatus
from app.models.payment import PaymentMethod
from app.models.project import MemberRole, ProjectStatus
from app.models.task import TaskStatus
from app.models.user import UserPlan, UserRole
from app.schemas.admin_extra import (
    AdminAuditLogResponse,
    AdminMaterialDetailResponse,
    AdminMemberAddRequest,
    AdminMaterialProjectRequest,
    AdminProjectDetailResponse,
    AdminProjectListItemResponse,
    AdminStatsResponse,
    AdminTaskCreateRequest,
    AnswerTemplateCreateRequest,
    AnswerTemplateResponse,
    AnswerTemplateUpdateRequest,
)
from app.schemas.common import PageResponse
from app.schemas.doc import ArchiveDocResponse, DocVersionResponse
from app.schemas.inquiry import AnswerCreateRequest, AnswerResponse, InquiryResponse
from app.schemas.notice import NoticeCreateRequest, NoticeResponse, NoticeUpdateRequest
from app.schemas.payment import AdminPaymentResponse
from app.schemas.project import LeaderDelegateRequest, MemberResponse, ProjectResponse, ProjectUpdateRequest
from app.schemas.task import TaskAssigneeResponse, TaskResponse, TaskStatusUpdateRequest, TaskUpdateRequest
from app.schemas.user import AdminPasswordResetRequest, AdminUserUpdateRequest, LoginHistoryResponse, UserResponse
from app.services.admin_audit import record_audit
from app.services.payment_service import apply_plan_change
from app.services.project_service import cascade_delete_project
from app.services.user_service import withdraw_user

router = APIRouter(prefix="/api/admin", tags=["Admin"], dependencies=[Depends(require_admin)])

_USER_SORT = {"created_at", "login_id", "name", "nickname", "email"}
_PROJECT_SORT = {"created_at", "name", "priority", "status"}
_INQUIRY_SORT = {"created_at", "status", "title"}
_DOC_SORT = {"created_at", "title"}
_TEMPLATE_SORT = {"created_at", "title"}
_AUDIT_SORT = {"created_at"}
_PAYMENT_SORT = {"created_at", "amount"}


def _doc_to_archive(doc: Doc) -> ArchiveDocResponse:
    latest = doc.latest_version
    return ArchiveDocResponse(
        id=doc.id,
        project_id=doc.project_id,
        project_name=doc.project.name if doc.project else None,
        user_id=doc.user_id,
        author_nickname=doc.author.nickname if doc.author else "",
        title=doc.title,
        content=doc.content,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        latest_version=DocVersionResponse.model_validate(latest) if latest else None,
    )


def _doc_to_detail(doc: Doc) -> AdminMaterialDetailResponse:
    base = _doc_to_archive(doc)
    versions = sorted(
        [v for v in (doc.versions or []) if not v.is_deleted],
        key=lambda v: v.version_no,
        reverse=True,
    )
    return AdminMaterialDetailResponse(
        **base.model_dump(),
        versions=[DocVersionResponse.model_validate(v) for v in versions],
    )


def _task_to_response(task: Task) -> TaskResponse:
    return TaskResponse(
        id=task.id,
        project_id=task.project_id,
        title=task.title,
        content=task.content,
        status=task.status,
        creator_id=task.creator_id,
        assignees=[TaskAssigneeResponse(id=u.id, nickname=u.nickname) for u in (task.assignees or [])],
        start_date=task.start_date,
        end_date=task.end_date,
        category=getattr(task, "category", None) or "기타",
        work_group=getattr(task, "work_group", None) or "",
        color=getattr(task, "color", None),
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _project_list_items(db: Session, projects: list[Project]) -> list[AdminProjectListItemResponse]:
    if not projects:
        return []
    ids = [p.id for p in projects]
    task_rows = db.execute(
        select(Task.project_id, Task.status, func.count())
        .where(Task.project_id.in_(ids))
        .group_by(Task.project_id, Task.status)
    ).all()
    counts: dict[int, dict[str, int]] = {}
    for pid, status, cnt in task_rows:
        bucket = counts.setdefault(pid, {"total": 0, "done": 0})
        bucket["total"] += int(cnt)
        if status == TaskStatus.DONE:
            bucket["done"] += int(cnt)

    member_rows = db.execute(
        select(ProjectMember.project_id, func.count())
        .where(ProjectMember.project_id.in_(ids))
        .group_by(ProjectMember.project_id)
    ).all()
    member_counts = {pid: int(cnt) for pid, cnt in member_rows}

    leader_rows = db.execute(
        select(ProjectMember.project_id, User.name)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id.in_(ids), ProjectMember.role == MemberRole.LEADER)
    ).all()
    leaders = {pid: name for pid, name in leader_rows}

    items = []
    for p in projects:
        base = ProjectResponse.model_validate(p)
        c = counts.get(p.id, {"total": 0, "done": 0})
        items.append(
            AdminProjectListItemResponse(
                **base.model_dump(),
                task_count=c["total"],
                task_done_count=c["done"],
                leader_name=leaders.get(p.id),
                member_count=member_counts.get(p.id, 0),
            )
        )
    return items


# ---------- Stats ----------


@router.get("/stats", response_model=AdminStatsResponse)
def admin_stats(db: Session = Depends(get_db)):
    users_total = db.scalar(select(func.count()).select_from(User)) or 0
    projects_total = db.scalar(select(func.count()).select_from(Project)) or 0
    projects_in_progress = (
        db.scalar(select(func.count()).select_from(Project).where(Project.status == ProjectStatus.IN_PROGRESS)) or 0
    )
    inquiries_pending = (
        db.scalar(select(func.count()).select_from(Inquiry).where(Inquiry.status == InquiryStatus.WAITING)) or 0
    )
    materials_total = db.scalar(select(func.count()).select_from(Doc)) or 0
    notices_total = db.scalar(select(func.count()).select_from(Notice)) or 0
    return AdminStatsResponse(
        users_total=users_total,
        projects_total=projects_total,
        projects_in_progress=projects_in_progress,
        inquiries_pending=inquiries_pending,
        materials_total=materials_total,
        notices_total=notices_total,
    )


# ---------- Users ----------


@router.get("/users", response_model=PageResponse[UserResponse])
def list_users(
    keyword: str | None = Query(None),
    page: int = Query(1),
    size: int = Query(DEFAULT_SIZE),
    sort: str | None = Query(None),
    db: Session = Depends(get_db),
):
    params = parse_page_params(page, size, sort, _USER_SORT)
    stmt = select(User)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(User.login_id.like(like), User.name.like(like), User.nickname.like(like), User.email.like(like))
        )
    return paginate(db, stmt, User, params)


@router.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None or user.is_deleted:
        raise not_found("회원을 찾을 수 없습니다.")
    return user


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    body: AdminUserUpdateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None or user.is_deleted:
        raise not_found("회원을 찾을 수 없습니다.")
    data = body.model_dump(exclude_unset=True)
    if "nickname" in data and data["nickname"] is not None:
        exists = db.scalar(
            select(User.id).where(User.nickname == data["nickname"], User.id != user_id).execution_options(include_deleted=True)
        )
        if exists:
            raise conflict(ErrorCode.DUPLICATE_NICKNAME, "이미 사용 중인 닉네임입니다.")
        user.nickname = data["nickname"]
    if "email" in data and data["email"] is not None:
        exists = db.scalar(
            select(User.id).where(User.email == data["email"], User.id != user_id).execution_options(include_deleted=True)
        )
        if exists:
            raise conflict(ErrorCode.DUPLICATE_EMAIL, "이미 사용 중인 이메일입니다.")
        user.email = data["email"]
    if "name" in data and data["name"] is not None:
        user.name = data["name"]
    if "plan" in data and data["plan"] is not None:
        if data["plan"] not in UserPlan.ALL:
            raise bad_request(message=f"plan은 {sorted(UserPlan.ALL)} 중 하나여야 합니다.")
        if data["plan"] != user.plan:
            apply_plan_change(db, user, next_plan=data["plan"], method=PaymentMethod.ADMIN)
    record_audit(db, admin, action="수정", target_type="user", target_id=user.id, target_label=user.name)
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/reset-password", response_model=UserResponse)
def reset_user_password(
    user_id: int,
    body: AdminPasswordResetRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None or user.is_deleted:
        raise not_found("회원을 찾을 수 없습니다.")
    if user.role == UserRole.SYSTEM_ADMIN:
        raise forbidden("시스템 관리자 비밀번호는 이 API로 변경할 수 없습니다.")
    user.password_hash = hash_password(body.new_password)
    record_audit(db, admin, action="비밀번호 리셋", target_type="user", target_id=user.id, target_label=user.name)
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/suspend", response_model=UserResponse)
def suspend_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None or user.is_deleted:
        raise not_found("회원을 찾을 수 없습니다.")
    if user.role == UserRole.SYSTEM_ADMIN:
        raise forbidden("시스템 관리자 계정은 정지할 수 없습니다.")
    user.is_suspended = True
    record_audit(db, admin, action="정지", target_type="user", target_id=user.id, target_label=user.name)
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/unsuspend", response_model=UserResponse)
def unsuspend_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None or user.is_deleted:
        raise not_found("회원을 찾을 수 없습니다.")
    user.is_suspended = False
    record_audit(db, admin, action="정지 해제", target_type="user", target_id=user.id, target_label=user.name)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users/{user_id}/login-history", response_model=PageResponse[LoginHistoryResponse])
def user_login_history(
    user_id: int,
    page: int = Query(1),
    size: int = Query(DEFAULT_SIZE),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None or user.is_deleted:
        raise not_found("회원을 찾을 수 없습니다.")
    params = parse_page_params(page, size, "created_at,desc", {"created_at"})
    stmt = select(LoginHistory).where(LoginHistory.user_id == user_id)
    return paginate(db, stmt, LoginHistory, params)


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None or user.is_deleted:
        raise not_found("회원을 찾을 수 없습니다.")
    if user.role == UserRole.SYSTEM_ADMIN:
        raise forbidden("시스템 관리자 계정은 삭제할 수 없습니다.")
    label = user.name
    withdraw_user(db, user)
    record_audit(db, admin, action="삭제", target_type="user", target_id=user_id, target_label=label)
    db.commit()


# ---------- Projects ----------


@router.get("/projects", response_model=PageResponse[AdminProjectListItemResponse])
def list_projects(
    keyword: str | None = Query(None),
    page: int = Query(1),
    size: int = Query(DEFAULT_SIZE),
    sort: str | None = Query(None),
    db: Session = Depends(get_db),
):
    params = parse_page_params(page, size, sort, _PROJECT_SORT)
    stmt = select(Project)
    if keyword:
        stmt = stmt.where(Project.name.like(f"%{keyword}%"))
    page_data = paginate(db, stmt, Project, params)
    page_data["items"] = _project_list_items(db, page_data["items"])
    return page_data


@router.get("/projects/{project_id}", response_model=AdminProjectDetailResponse)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.scalar(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.members).selectinload(ProjectMember.user))
    )
    if project is None or project.is_deleted:
        raise not_found("프로젝트를 찾을 수 없습니다.")
    tasks = list(
        db.scalars(
            select(Task)
            .where(Task.project_id == project_id)
            .options(selectinload(Task.assignees))
            .order_by(Task.id.desc())
        )
    )
    members = [
        MemberResponse(
            user_id=m.user_id,
            name=m.user.name if m.user else "",
            nickname=m.user.nickname if m.user else "",
            role=m.role,
            joined_at=m.joined_at,
        )
        for m in project.members
    ]
    base = ProjectResponse.model_validate(project)
    return AdminProjectDetailResponse(
        **base.model_dump(),
        members=members,
        tasks=[_task_to_response(t) for t in tasks],
    )


@router.patch("/projects/{project_id}", response_model=AdminProjectDetailResponse)
def update_project(
    project_id: int,
    body: ProjectUpdateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if project is None or project.is_deleted:
        raise not_found("프로젝트를 찾을 수 없습니다.")
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(project, field, value)
    record_audit(db, admin, action="수정", target_type="project", target_id=project.id, target_label=project.name)
    db.commit()
    return get_project(project_id, db)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None or project.is_deleted:
        raise not_found("프로젝트를 찾을 수 없습니다.")
    label = project.name
    cascade_delete_project(db, project)
    record_audit(db, admin, action="삭제", target_type="project", target_id=project_id, target_label=label)
    db.commit()


def _require_project(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.is_deleted:
        raise not_found("프로젝트를 찾을 수 없습니다.")
    return project


def _member_responses(db: Session, project_id: int) -> list[MemberResponse]:
    rows = db.scalars(
        select(ProjectMember)
        .where(ProjectMember.project_id == project_id)
        .options(selectinload(ProjectMember.user))
        .order_by(ProjectMember.joined_at.asc(), ProjectMember.id.asc())
    ).all()
    return [
        MemberResponse(
            user_id=m.user_id,
            name=m.user.name if m.user else "",
            nickname=m.user.nickname if m.user else "",
            role=m.role,
            joined_at=m.joined_at,
        )
        for m in rows
    ]


def _resolve_admin_assignees(db: Session, project_id: int, assignee_ids: list[int]) -> list[User]:
    ids = list(dict.fromkeys(assignee_ids))
    member_ids = set(
        db.scalars(
            select(ProjectMember.user_id).where(
                ProjectMember.project_id == project_id, ProjectMember.user_id.in_(ids)
            )
        )
    )
    invalid = [i for i in ids if i not in member_ids]
    if invalid:
        raise bad_request(message=f"담당자는 프로젝트 멤버여야 합니다: {invalid}")
    return list(db.scalars(select(User).where(User.id.in_(ids))))


@router.put("/projects/{project_id}/leader", response_model=list[MemberResponse])
def admin_delegate_leader(
    project_id: int,
    body: LeaderDelegateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    project = _require_project(db, project_id)
    target = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == body.user_id
        )
    )
    if target is None:
        raise not_found("해당 멤버를 찾을 수 없습니다.")
    if target.role != MemberRole.LEADER:
        current = db.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id, ProjectMember.role == MemberRole.LEADER
            )
        )
        if current is not None:
            current.role = MemberRole.MEMBER
        target.role = MemberRole.LEADER
    record_audit(
        db,
        admin,
        action="팀장 변경",
        target_type="project",
        target_id=project.id,
        target_label=project.name,
        detail=f"user_id={body.user_id}",
    )
    db.commit()
    return _member_responses(db, project_id)


@router.post("/projects/{project_id}/members", response_model=list[MemberResponse], status_code=201)
def admin_add_member(
    project_id: int,
    body: AdminMemberAddRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    project = _require_project(db, project_id)
    user = db.get(User, body.user_id)
    if user is None or user.is_deleted:
        raise not_found("회원을 찾을 수 없습니다.")
    exists = db.scalar(
        select(ProjectMember.id).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == body.user_id
        )
    )
    if exists:
        raise conflict(ErrorCode.ALREADY_JOINED, "이미 프로젝트 멤버입니다.")
    db.add(ProjectMember(project_id=project_id, user_id=body.user_id, role=MemberRole.MEMBER))
    record_audit(
        db,
        admin,
        action="팀원 추가",
        target_type="project",
        target_id=project.id,
        target_label=project.name,
        detail=f"user_id={body.user_id}",
    )
    db.commit()
    return _member_responses(db, project_id)


@router.delete("/projects/{project_id}/members/{user_id}", status_code=204)
def admin_kick_member(
    project_id: int,
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    project = _require_project(db, project_id)
    target = db.scalar(
        select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
    )
    if target is None:
        raise not_found("해당 멤버를 찾을 수 없습니다.")
    if target.role == MemberRole.LEADER:
        raise conflict(ErrorCode.LEADER_CANNOT_LEAVE, "팀장은 위임 후에만 방출할 수 있습니다.")
    db.delete(target)
    record_audit(
        db,
        admin,
        action="팀원 방출",
        target_type="project",
        target_id=project.id,
        target_label=project.name,
        detail=f"user_id={user_id}",
    )
    db.commit()


@router.post("/projects/{project_id}/tasks", response_model=TaskResponse, status_code=201)
def admin_create_task(
    project_id: int,
    body: AdminTaskCreateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from datetime import date as date_cls

    project = _require_project(db, project_id)
    end = body.end_date or project.end_date or date_cls.today()
    start = body.start_date or project.start_date or end
    if start > end:
        start = end
    assignee_id = body.assignee_id
    if assignee_id is None:
        leader = db.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id, ProjectMember.role == MemberRole.LEADER
            )
        )
        if leader is None:
            raise bad_request(message="담당자를 지정하거나 팀장이 있는 프로젝트여야 합니다.")
        assignee_id = leader.user_id
    assignees = _resolve_admin_assignees(db, project_id, [assignee_id])
    task = Task(
        project_id=project_id,
        title=body.title,
        content=None,
        creator_id=admin.id,
        start_date=start,
        end_date=end,
        status=body.status,
        assignees=assignees,
        category="기타",
        work_group="",
    )
    db.add(task)
    record_audit(
        db,
        admin,
        action="태스크 추가",
        target_type="project",
        target_id=project.id,
        target_label=project.name,
        detail=body.title,
    )
    db.commit()
    db.refresh(task)
    task = db.scalar(select(Task).where(Task.id == task.id).options(selectinload(Task.assignees)))
    return _task_to_response(task)


@router.patch("/projects/{project_id}/tasks/{task_id}", response_model=TaskResponse)
def admin_update_task(
    project_id: int,
    task_id: int,
    body: TaskUpdateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _require_project(db, project_id)
    task = db.scalar(
        select(Task)
        .where(Task.id == task_id, Task.project_id == project_id)
        .options(selectinload(Task.assignees))
    )
    if task is None or task.is_deleted:
        raise not_found("업무를 찾을 수 없습니다.")
    data = body.model_dump(exclude_unset=True)
    if "assignee_ids" in data:
        ids = data.pop("assignee_ids")
        if not ids:
            raise bad_request(message="담당자는 최소 1명이어야 합니다.")
        task.assignees = _resolve_admin_assignees(db, project_id, ids)
    for field, value in data.items():
        setattr(task, field, value)
    record_audit(
        db,
        admin,
        action="태스크 수정",
        target_type="task",
        target_id=task.id,
        target_label=task.title,
    )
    db.commit()
    db.refresh(task)
    return _task_to_response(task)


@router.patch("/projects/{project_id}/tasks/{task_id}/status", response_model=TaskResponse)
def admin_update_task_status(
    project_id: int,
    task_id: int,
    body: TaskStatusUpdateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _require_project(db, project_id)
    task = db.scalar(
        select(Task)
        .where(Task.id == task_id, Task.project_id == project_id)
        .options(selectinload(Task.assignees))
    )
    if task is None or task.is_deleted:
        raise not_found("업무를 찾을 수 없습니다.")
    task.status = body.status
    record_audit(
        db,
        admin,
        action="태스크 상태 변경",
        target_type="task",
        target_id=task.id,
        target_label=task.title,
        detail=body.status,
    )
    db.commit()
    db.refresh(task)
    return _task_to_response(task)


@router.delete("/projects/{project_id}/tasks/{task_id}", status_code=204)
def admin_delete_task(
    project_id: int,
    task_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    project = _require_project(db, project_id)
    task = db.scalar(select(Task).where(Task.id == task_id, Task.project_id == project_id))
    if task is None or task.is_deleted:
        raise not_found("업무를 찾을 수 없습니다.")
    label = task.title
    task.soft_delete()
    record_audit(
        db,
        admin,
        action="태스크 삭제",
        target_type="task",
        target_id=task_id,
        target_label=label,
        detail=f"project_id={project.id}",
    )
    db.commit()


# ---------- Notices ----------


@router.post("/notices", response_model=NoticeResponse, status_code=201)
def create_notice(body: NoticeCreateRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    notice = Notice(
        user_id=admin.id, title=body.title, body=body.body, category=body.category, pinned=body.pinned
    )
    db.add(notice)
    record_audit(db, admin, action="등록", target_type="notice", target_label=body.title)
    db.commit()
    db.refresh(notice)
    return notice


def _get_notice(db: Session, notice_id: int) -> Notice:
    notice = db.scalar(select(Notice).where(Notice.id == notice_id))
    if notice is None:
        raise not_found("공지사항을 찾을 수 없습니다.")
    return notice


@router.patch("/notices/{notice_id}", response_model=NoticeResponse)
def update_notice(
    notice_id: int,
    body: NoticeUpdateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    notice = _get_notice(db, notice_id)
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        if value is not None:
            setattr(notice, field, value)
    record_audit(db, admin, action="수정", target_type="notice", target_id=notice.id, target_label=notice.title)
    db.commit()
    db.refresh(notice)
    return notice


@router.delete("/notices/{notice_id}", status_code=204)
def delete_notice(notice_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    notice = _get_notice(db, notice_id)
    label = notice.title
    notice.soft_delete()
    record_audit(db, admin, action="삭제", target_type="notice", target_id=notice_id, target_label=label)
    db.commit()


# ---------- Inquiries ----------


@router.get("/inquiries", response_model=PageResponse[InquiryResponse])
def list_all_inquiries(
    status: str | None = Query(None),
    page: int = Query(1),
    size: int = Query(DEFAULT_SIZE),
    sort: str | None = Query(None),
    db: Session = Depends(get_db),
):
    if status is not None and status not in InquiryStatus.ALL:
        raise bad_request(message=f"status 필터는 {sorted(InquiryStatus.ALL)} 중 하나여야 합니다.")
    params = parse_page_params(page, size, sort, _INQUIRY_SORT)
    stmt = select(Inquiry).options(selectinload(Inquiry.answer))
    if status is not None:
        stmt = stmt.where(Inquiry.status == status)
    return paginate(db, stmt, Inquiry, params)


@router.delete("/inquiries/{question_id}", status_code=204)
def delete_inquiry_admin(
    question_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    inquiry = db.scalar(select(Inquiry).where(Inquiry.id == question_id).options(selectinload(Inquiry.answer)))
    if inquiry is None or inquiry.is_deleted:
        raise not_found("문의를 찾을 수 없습니다.")
    label = inquiry.title
    if inquiry.answer is not None and not inquiry.answer.is_deleted:
        inquiry.answer.soft_delete()
    inquiry.soft_delete()
    record_audit(db, admin, action="삭제", target_type="inquiry", target_id=question_id, target_label=label)
    db.commit()


@router.patch("/inquiries/{question_id}/answer", response_model=AnswerResponse)
def update_inquiry_answer(
    question_id: int,
    body: AnswerCreateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    inquiry = db.scalar(select(Inquiry).where(Inquiry.id == question_id).options(selectinload(Inquiry.answer)))
    if inquiry is None or inquiry.is_deleted:
        raise not_found("문의를 찾을 수 없습니다.")
    if inquiry.answer is None or inquiry.answer.is_deleted:
        raise not_found("등록된 답변이 없습니다. 먼저 답변을 등록하세요.")
    inquiry.answer.content = body.content
    record_audit(
        db,
        admin,
        action="답변 수정",
        target_type="inquiry",
        target_id=question_id,
        target_label=inquiry.title,
    )
    db.commit()
    db.refresh(inquiry.answer)
    return inquiry.answer


# ---------- Materials ----------


@router.get("/materials", response_model=PageResponse[ArchiveDocResponse])
def list_materials(
    keyword: str | None = Query(None),
    page: int = Query(1),
    size: int = Query(DEFAULT_SIZE),
    sort: str | None = Query(None),
    db: Session = Depends(get_db),
):
    params = parse_page_params(page, size, sort, _DOC_SORT)
    stmt = select(Doc).options(selectinload(Doc.versions), selectinload(Doc.author), selectinload(Doc.project))
    if keyword:
        stmt = stmt.where(Doc.title.like(f"%{keyword}%"))
    page_data = paginate(db, stmt, Doc, params)
    page_data["items"] = [_doc_to_archive(d) for d in page_data["items"]]
    return page_data


@router.get("/materials/{doc_id}", response_model=AdminMaterialDetailResponse)
def get_material(doc_id: int, db: Session = Depends(get_db)):
    doc = db.scalar(
        select(Doc)
        .where(Doc.id == doc_id)
        .options(
            selectinload(Doc.versions).selectinload(DocVersion.uploader),
            selectinload(Doc.author),
            selectinload(Doc.project),
        )
    )
    if doc is None or doc.is_deleted:
        raise not_found("자료를 찾을 수 없습니다.")
    return _doc_to_detail(doc)


@router.get("/materials/{doc_id}/versions/{version_id}/download")
def download_material_version(doc_id: int, version_id: int, db: Session = Depends(get_db)):
    doc = db.get(Doc, doc_id)
    if doc is None or doc.is_deleted:
        raise not_found("자료를 찾을 수 없습니다.")
    version = db.get(DocVersion, version_id)
    if version is None or version.is_deleted or version.doc_id != doc_id:
        raise not_found("버전을 찾을 수 없습니다.")
    return stream_download(version.stored_name, version.file_name, version.mime_type)


@router.delete("/materials/{doc_id}", status_code=204)
def delete_material(doc_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    doc = db.scalar(select(Doc).where(Doc.id == doc_id).options(selectinload(Doc.versions)))
    if doc is None or doc.is_deleted:
        raise not_found("자료를 찾을 수 없습니다.")
    label = doc.title
    for v in doc.versions:
        if not v.is_deleted:
            v.soft_delete()
    doc.soft_delete()
    record_audit(db, admin, action="삭제", target_type="material", target_id=doc_id, target_label=label)
    db.commit()


@router.patch("/materials/{doc_id}/project", response_model=AdminMaterialDetailResponse)
def set_material_project(
    doc_id: int,
    body: AdminMaterialProjectRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    doc = db.scalar(
        select(Doc)
        .where(Doc.id == doc_id)
        .options(selectinload(Doc.versions), selectinload(Doc.author), selectinload(Doc.project))
    )
    if doc is None or doc.is_deleted:
        raise not_found("자료를 찾을 수 없습니다.")
    if body.project_id is not None:
        project = _require_project(db, body.project_id)
        doc.project_id = project.id
        detail = f"project_id={project.id}"
    else:
        doc.project_id = None
        detail = "project_id=null"
    record_audit(
        db,
        admin,
        action="자료 연결",
        target_type="material",
        target_id=doc.id,
        target_label=doc.title,
        detail=detail,
    )
    db.commit()
    db.refresh(doc)
    doc = db.scalar(
        select(Doc)
        .where(Doc.id == doc_id)
        .options(selectinload(Doc.versions), selectinload(Doc.author), selectinload(Doc.project))
    )
    return _doc_to_detail(doc)


# ---------- Templates ----------


@router.get("/templates", response_model=PageResponse[AnswerTemplateResponse])
def list_templates(
    page: int = Query(1),
    size: int = Query(DEFAULT_SIZE),
    sort: str | None = Query(None),
    db: Session = Depends(get_db),
):
    params = parse_page_params(page, size, sort, _TEMPLATE_SORT)
    stmt = select(AnswerTemplate)
    return paginate(db, stmt, AnswerTemplate, params)


@router.post("/templates", response_model=AnswerTemplateResponse, status_code=201)
def create_template(
    body: AnswerTemplateCreateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    tpl = AnswerTemplate(title=body.title, content=body.content, created_by=admin.id)
    db.add(tpl)
    record_audit(db, admin, action="템플릿 추가", target_type="template", target_label=body.title)
    db.commit()
    db.refresh(tpl)
    return tpl


@router.patch("/templates/{template_id}", response_model=AnswerTemplateResponse)
def update_template(
    template_id: int,
    body: AnswerTemplateUpdateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    tpl = db.get(AnswerTemplate, template_id)
    if tpl is None or tpl.is_deleted:
        raise not_found("템플릿을 찾을 수 없습니다.")
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        if value is not None:
            setattr(tpl, field, value)
    record_audit(db, admin, action="템플릿 수정", target_type="template", target_id=tpl.id, target_label=tpl.title)
    db.commit()
    db.refresh(tpl)
    return tpl


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(template_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    tpl = db.get(AnswerTemplate, template_id)
    if tpl is None or tpl.is_deleted:
        raise not_found("템플릿을 찾을 수 없습니다.")
    label = tpl.title
    tpl.soft_delete()
    record_audit(db, admin, action="템플릿 삭제", target_type="template", target_id=template_id, target_label=label)
    db.commit()


# ---------- Audit logs ----------


@router.get("/audit-logs", response_model=PageResponse[AdminAuditLogResponse])
def list_audit_logs(
    page: int = Query(1),
    size: int = Query(DEFAULT_SIZE),
    sort: str | None = Query(None),
    db: Session = Depends(get_db),
):
    params = parse_page_params(page, size, sort or "created_at,desc", _AUDIT_SORT)
    stmt = select(AdminAuditLog)
    return paginate(db, stmt, AdminAuditLog, params)


# ---------- Payments ----------


@router.get("/payments", response_model=PageResponse[AdminPaymentResponse])
def list_payments(
    keyword: str | None = Query(None),
    kind: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1),
    size: int = Query(DEFAULT_SIZE),
    sort: str | None = Query(None),
    db: Session = Depends(get_db),
):
    params = parse_page_params(page, size, sort or "created_at,desc", _PAYMENT_SORT)
    stmt = select(Payment)
    if kind:
        stmt = stmt.where(Payment.kind == kind)
    if status:
        stmt = stmt.where(Payment.status == status)
    if keyword:
        like = f"%{keyword}%"
        user_ids = select(User.id).where(
            or_(User.login_id.like(like), User.name.like(like), User.email.like(like), User.nickname.like(like))
        )
        stmt = stmt.where(or_(Payment.order_id.like(like), Payment.user_id.in_(user_ids)))

    page_data = paginate(db, stmt, Payment, params)
    items = page_data["items"]
    if not items:
        return page_data

    uids = {p.user_id for p in items}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(uids)).execution_options(include_deleted=True))}
    page_data["items"] = [
        AdminPaymentResponse(
            id=p.id,
            user_id=p.user_id,
            amount=p.amount,
            currency=p.currency,
            plan=p.plan,
            kind=p.kind,
            status=p.status,
            method=p.method,
            order_id=p.order_id,
            payer_name=p.payer_name,
            payer_email=p.payer_email,
            note=p.note,
            created_at=p.created_at,
            updated_at=p.updated_at,
            user_login_id=(users.get(p.user_id).login_id if users.get(p.user_id) else ""),
            user_name=(users.get(p.user_id).name if users.get(p.user_id) else ""),
            user_email=(users.get(p.user_id).email if users.get(p.user_id) else ""),
        )
        for p in items
    ]
    return page_data
