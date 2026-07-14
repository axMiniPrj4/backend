from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import require_admin
from app.core.errors import bad_request, not_found
from app.core.pagination import DEFAULT_SIZE, parse_page_params, paginate
from app.db.session import get_db
from app.models import Inquiry, Notice, Project, User
from app.models.inquiry import InquiryStatus
from app.schemas.common import PageResponse
from app.schemas.inquiry import InquiryResponse
from app.schemas.notice import NoticeCreateRequest, NoticeResponse, NoticeUpdateRequest
from app.schemas.project import ProjectResponse
from app.schemas.user import UserResponse
from app.services.project_service import cascade_delete_project
from app.services.user_service import withdraw_user

router = APIRouter(prefix="/api/admin", tags=["Admin"], dependencies=[Depends(require_admin)])

_USER_SORT = {"created_at", "login_id", "name", "nickname", "email"}
_PROJECT_SORT = {"created_at", "name", "priority", "status"}
_INQUIRY_SORT = {"created_at", "status", "title"}


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


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None or user.is_deleted:
        raise not_found("회원을 찾을 수 없습니다.")
    # 기준안 #3: 본인 탈퇴와 동일 로직 — LEADER인 프로젝트 존재 시 409
    withdraw_user(db, user)


@router.get("/projects", response_model=PageResponse[ProjectResponse])
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
    return paginate(db, stmt, Project, params)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None or project.is_deleted:
        raise not_found("프로젝트를 찾을 수 없습니다.")
    # 기준안 #4: LEADER 삭제와 동일한 cascade Soft Delete
    cascade_delete_project(db, project)


@router.post("/notices", response_model=NoticeResponse, status_code=201)
def create_notice(body: NoticeCreateRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    notice = Notice(
        user_id=admin.id, title=body.title, body=body.body, category=body.category, pinned=body.pinned
    )
    db.add(notice)
    db.commit()
    return notice


def _get_notice(db: Session, notice_id: int) -> Notice:
    notice = db.scalar(select(Notice).where(Notice.id == notice_id))
    if notice is None:
        raise not_found("공지사항을 찾을 수 없습니다.")
    return notice


@router.patch("/notices/{notice_id}", response_model=NoticeResponse)
def update_notice(notice_id: int, body: NoticeUpdateRequest, db: Session = Depends(get_db)):
    notice = _get_notice(db, notice_id)
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        if value is not None:
            setattr(notice, field, value)
    db.commit()
    return notice


@router.delete("/notices/{notice_id}", status_code=204)
def delete_notice(notice_id: int, db: Session = Depends(get_db)):
    notice = _get_notice(db, notice_id)
    notice.soft_delete()
    db.commit()


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
