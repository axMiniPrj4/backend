from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_user
from app.core.errors import ErrorCode, bad_request, conflict, forbidden, not_found
from app.core.files import delete_stored_file, save_upload
from app.core.pagination import DEFAULT_SIZE, parse_page_params, paginate
from app.db.session import get_db
from app.models import Answer, Inquiry, Project, ProjectMember, User
from app.models.inquiry import InquiryStatus
from app.models.user import UserRole
from app.schemas.common import PageResponse
from app.schemas.inquiry import AnswerCreateRequest, AnswerResponse, InquiryResponse, InquiryUpdateRequest

router = APIRouter(prefix="/api/inquiries", tags=["Inquiry"])

_SORT_FIELDS = {"created_at", "status", "title"}
_SUBDIR = "inquiries"


def _get_inquiry_or_404(db: Session, question_id: int) -> Inquiry:
    inquiry = db.scalar(
        select(Inquiry).where(Inquiry.id == question_id).options(selectinload(Inquiry.answer))
    )
    if inquiry is None:
        raise not_found("문의를 찾을 수 없습니다.")
    return inquiry


@router.post("", response_model=InquiryResponse, status_code=201)
def create_inquiry(
    title: str = Form(min_length=1, max_length=200),
    content: str = Form(min_length=1),
    project_id: int | None = Form(None),  # 일반 문의는 NULL
    file: UploadFile | None = File(None),  # 첨부 선택 1개 (자료실과 동일 제한 — 기준안 #10)
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if project_id is not None:
        project = db.get(Project, project_id)
        if project is None or project.is_deleted:
            raise bad_request(message="존재하지 않는 프로젝트입니다.")
        is_member = db.scalar(
            select(ProjectMember.id).where(
                ProjectMember.project_id == project_id, ProjectMember.user_id == user.id
            )
        )
        if not is_member:
            raise bad_request(message="참여 중인 프로젝트만 지정할 수 있습니다.")

    stored = save_upload(file, _SUBDIR) if file is not None and file.filename else None
    try:
        inquiry = Inquiry(
            user_id=user.id,
            project_id=project_id,
            title=title,
            content=content,
            file_name=stored.file_name if stored else None,
            stored_name=stored.stored_name if stored else None,
            file_size=stored.file_size if stored else None,
            mime_type=stored.mime_type if stored else None,
        )
        db.add(inquiry)
        db.commit()
    except Exception:
        db.rollback()
        if stored:
            delete_stored_file(stored.stored_name)
        raise
    return inquiry


@router.get("", response_model=PageResponse[InquiryResponse])
def list_my_inquiries(
    status: str | None = Query(None),
    page: int = Query(1),
    size: int = Query(DEFAULT_SIZE),
    sort: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if status is not None and status not in InquiryStatus.ALL:
        raise bad_request(message=f"status 필터는 {sorted(InquiryStatus.ALL)} 중 하나여야 합니다.")
    params = parse_page_params(page, size, sort, _SORT_FIELDS)
    stmt = select(Inquiry).where(Inquiry.user_id == user.id).options(selectinload(Inquiry.answer))
    if status is not None:
        stmt = stmt.where(Inquiry.status == status)
    return paginate(db, stmt, Inquiry, params)


@router.get("/{question_id}", response_model=InquiryResponse)
def get_inquiry(question_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    inquiry = _get_inquiry_or_404(db, question_id)
    # 본인 것만 조회 가능. SYSTEM_ADMIN은 전체 조회 가능
    if inquiry.user_id != user.id and user.role != UserRole.SYSTEM_ADMIN:
        raise forbidden("본인의 문의만 조회할 수 있습니다.")
    return inquiry


@router.patch("/{question_id}", response_model=InquiryResponse)
def update_inquiry(
    question_id: int,
    body: InquiryUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    inquiry = _get_inquiry_or_404(db, question_id)
    if inquiry.user_id != user.id:
        raise forbidden("본인의 문의만 수정할 수 있습니다.")
    if inquiry.status != InquiryStatus.WAITING:
        raise conflict(ErrorCode.ALREADY_ANSWERED, "답변이 완료된 문의는 수정할 수 없습니다.")
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(inquiry, field, value)
    db.commit()
    return inquiry


@router.delete("/{question_id}", status_code=204)
def delete_inquiry(question_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    inquiry = _get_inquiry_or_404(db, question_id)
    if inquiry.user_id != user.id:
        raise forbidden("본인의 문의만 삭제할 수 있습니다.")
    if inquiry.status != InquiryStatus.WAITING:
        raise conflict(ErrorCode.ALREADY_ANSWERED, "답변이 완료된 문의는 삭제할 수 없습니다.")
    inquiry.soft_delete()
    db.commit()


@router.post("/{question_id}/answer", response_model=AnswerResponse, status_code=201)
def create_answer(
    question_id: int,
    body: AnswerCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # SYSTEM_ADMIN만 답변 가능
    if user.role != UserRole.SYSTEM_ADMIN:
        raise forbidden("관리자만 답변할 수 있습니다.")
    inquiry = _get_inquiry_or_404(db, question_id)
    if inquiry.answer is not None and not inquiry.answer.is_deleted:
        raise conflict(ErrorCode.ANSWER_EXISTS, "이미 답변이 등록된 문의입니다.")
    # 단일 트랜잭션: answer INSERT + inquiry.status → ANSWERED
    answer = Answer(question_id=inquiry.id, user_id=user.id, content=body.content)
    db.add(answer)
    inquiry.status = InquiryStatus.ANSWERED
    db.commit()
    return answer
