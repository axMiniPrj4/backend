"""전역 자료실 — 공통 자료(project_id NULL) + 내가 참여한 프로젝트 자료.

권한 (기준안, 2026-07-14):
- 공통 자료: 등록·조회는 로그인 사용자 누구나 / 수정·삭제·새 버전 업로드·버전 삭제는 작성자 본인만
- 프로젝트 자료: 기존 규칙 그대로 (멤버 조회·버전 업로드, 수정·삭제는 작성자 또는 LEADER)
"""
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_user
from app.core.errors import ErrorCode, conflict, forbidden, not_found
from app.core.files import delete_stored_file, save_upload, stream_download
from app.core.pagination import parse_page_params, paginate
from app.db.base import utcnow
from app.db.session import get_db
from app.models import Doc, DocVersion, ProjectMember, User
from app.models.project import MemberRole
from app.schemas.common import PageResponse
from app.schemas.doc import ArchiveDocResponse, DocUpdateRequest, DocVersionResponse

router = APIRouter(prefix="/api/archive", tags=["Archive"])

_SORT_FIELDS = {"created_at", "title"}
_SUBDIR = "archive"


def _to_response(doc: Doc) -> ArchiveDocResponse:
    latest = doc.latest_version
    return ArchiveDocResponse(
        id=doc.id,
        project_id=doc.project_id,
        project_name=doc.project.name if doc.project else None,
        user_id=doc.user_id,
        author_nickname=doc.author.nickname,
        title=doc.title,
        content=doc.content,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        latest_version=DocVersionResponse.model_validate(latest) if latest else None,
    )


def _my_project_ids(user: User):
    return select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)


def _get_accessible_doc(db: Session, user: User, doc_id: int) -> Doc:
    """공통 자료는 누구나, 프로젝트 자료는 멤버만 접근 가능."""
    doc = db.scalar(
        select(Doc)
        .where(Doc.id == doc_id)
        .options(selectinload(Doc.versions), selectinload(Doc.author), selectinload(Doc.project))
    )
    if doc is None or (doc.project_id is not None and (doc.project is None or doc.project.is_deleted)):
        raise not_found("자료를 찾을 수 없습니다.")
    if doc.project_id is not None:
        member = db.scalar(
            select(ProjectMember.id).where(
                ProjectMember.project_id == doc.project_id, ProjectMember.user_id == user.id
            )
        )
        if member is None:
            raise forbidden("프로젝트 멤버가 아닙니다.")
    return doc


def _can_manage(db: Session, user: User, doc: Doc) -> bool:
    """수정·삭제 권한 — 공통: 작성자 / 프로젝트: 작성자 또는 LEADER."""
    if doc.user_id == user.id:
        return True
    if doc.project_id is None:
        return False
    role = db.scalar(
        select(ProjectMember.role).where(
            ProjectMember.project_id == doc.project_id, ProjectMember.user_id == user.id
        )
    )
    return role == MemberRole.LEADER


def _require_manage(db: Session, user: User, doc: Doc, action: str):
    if not _can_manage(db, user, doc):
        who = "작성자" if doc.project_id is None else "작성자 또는 팀장"
        raise forbidden(f"{who}만 {action}할 수 있습니다.")


@router.post("", response_model=ArchiveDocResponse, status_code=201)
def create_common_doc(
    title: str = Form(min_length=1, max_length=200),
    content: str | None = Form(None),
    file: UploadFile = File(...),  # 파일 필수 → version 1 자동 생성 (기존 정책 동일)
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """공통 자료 등록 — 로그인 사용자 누구나. project_id 없이 생성."""
    stored = save_upload(file, _SUBDIR)
    try:
        doc = Doc(project_id=None, user_id=user.id, title=title, content=content)
        db.add(doc)
        db.flush()
        db.add(
            DocVersion(
                doc_id=doc.id,
                version_no=1,
                file_name=stored.file_name,
                stored_name=stored.stored_name,
                file_size=stored.file_size,
                mime_type=stored.mime_type,
                uploaded_by=user.id,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        delete_stored_file(stored.stored_name)
        raise
    return _to_response(_get_accessible_doc(db, user, doc.id))


@router.get("", response_model=PageResponse[ArchiveDocResponse])
def list_archive(
    q: str | None = Query(None, description="제목 검색"),
    project_id: int | None = Query(None, description="특정 프로젝트만"),
    common_only: bool = Query(False, description="공통 자료만"),
    page: int = Query(1),
    size: int = Query(10),
    sort: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """전역 자료 목록 — 공통 자료 + 내가 참여한 프로젝트의 자료."""
    params = parse_page_params(page, size, sort, _SORT_FIELDS)
    stmt = (
        select(Doc)
        .where(or_(Doc.project_id.is_(None), Doc.project_id.in_(_my_project_ids(user))))
        .options(selectinload(Doc.versions), selectinload(Doc.author), selectinload(Doc.project))
    )
    if common_only:
        stmt = stmt.where(Doc.project_id.is_(None))
    elif project_id is not None:
        is_member = db.scalar(
            select(ProjectMember.id).where(
                ProjectMember.project_id == project_id, ProjectMember.user_id == user.id
            )
        )
        if not is_member:
            raise forbidden("프로젝트 멤버가 아닙니다.")
        stmt = stmt.where(Doc.project_id == project_id)
    if q:
        stmt = stmt.where(Doc.title.like(f"%{q}%"))
    page_data = paginate(db, stmt, Doc, params)
    page_data["items"] = [_to_response(d) for d in page_data["items"]]
    return page_data


@router.get("/{doc_id}", response_model=ArchiveDocResponse)
def get_archive_doc(doc_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _to_response(_get_accessible_doc(db, user, doc_id))


@router.get("/{doc_id}/file")
def download_latest(doc_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    doc = _get_accessible_doc(db, user, doc_id)
    latest = doc.latest_version
    if latest is None:
        raise not_found("다운로드할 파일이 없습니다.")
    return stream_download(latest.stored_name, latest.file_name, latest.mime_type)


@router.patch("/{doc_id}", response_model=ArchiveDocResponse)
def update_archive_doc(
    doc_id: int,
    body: DocUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = _get_accessible_doc(db, user, doc_id)
    _require_manage(db, user, doc, "수정")
    data = body.model_dump(exclude_unset=True)

    if "project_id" in data:
        new_pid = data.pop("project_id")
        if new_pid is not None:
            is_member = db.scalar(
                select(ProjectMember.id).where(
                    ProjectMember.project_id == new_pid, ProjectMember.user_id == user.id
                )
            )
            if is_member is None:
                raise forbidden("이동할 프로젝트의 멤버가 아닙니다.")
        doc.project_id = new_pid

    for field, value in data.items():
        setattr(doc, field, value)
    db.commit()
    db.expire(doc)
    return _to_response(_get_accessible_doc(db, user, doc.id))


@router.delete("/{doc_id}", status_code=204)
def delete_archive_doc(doc_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    doc = _get_accessible_doc(db, user, doc_id)
    _require_manage(db, user, doc, "삭제")
    now = utcnow()
    for v in doc.versions:
        if not v.is_deleted:
            v.deleted_at = now
    doc.deleted_at = now
    db.commit()


# ---------- 버전 관리 (공통/프로젝트 자료 모두 지원) ----------


@router.post("/{doc_id}/versions", response_model=DocVersionResponse, status_code=201)
def upload_version(
    doc_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """새 버전 업로드 — 공통 자료는 작성자만, 프로젝트 자료는 멤버 누구나(기존 정책)."""
    doc = _get_accessible_doc(db, user, doc_id)
    if doc.project_id is None and doc.user_id != user.id:
        raise forbidden("공통 자료의 새 버전은 작성자만 올릴 수 있습니다.")
    stored = save_upload(file, _SUBDIR)
    try:
        max_no = db.scalar(
            select(func.max(DocVersion.version_no))
            .where(DocVersion.doc_id == doc.id)
            .execution_options(include_deleted=True)
        ) or 0
        version = DocVersion(
            doc_id=doc.id,
            version_no=max_no + 1,
            file_name=stored.file_name,
            stored_name=stored.stored_name,
            file_size=stored.file_size,
            mime_type=stored.mime_type,
            uploaded_by=user.id,
        )
        db.add(version)
        db.commit()
    except Exception:
        db.rollback()
        delete_stored_file(stored.stored_name)
        raise
    return version


@router.get("/{doc_id}/versions", response_model=list[DocVersionResponse])
def list_versions(doc_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    doc = _get_accessible_doc(db, user, doc_id)
    return db.scalars(
        select(DocVersion).where(DocVersion.doc_id == doc.id).order_by(DocVersion.version_no.desc())
    ).all()


def _get_version(db: Session, doc: Doc, version_no: int) -> DocVersion:
    version = db.scalar(
        select(DocVersion).where(DocVersion.doc_id == doc.id, DocVersion.version_no == version_no)
    )
    if version is None:
        raise not_found("해당 버전을 찾을 수 없습니다.")
    return version


@router.get("/{doc_id}/versions/{version_no}/file")
def download_version(
    doc_id: int,
    version_no: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = _get_accessible_doc(db, user, doc_id)
    version = _get_version(db, doc, version_no)
    return stream_download(version.stored_name, version.file_name, version.mime_type)


@router.delete("/{doc_id}/versions/{version_no}", status_code=204)
def delete_version(
    doc_id: int,
    version_no: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = _get_accessible_doc(db, user, doc_id)
    version = _get_version(db, doc, version_no)
    if doc.project_id is None:
        if doc.user_id != user.id:
            raise forbidden("공통 자료의 버전은 작성자만 삭제할 수 있습니다.")
    else:
        # 프로젝트 자료: 업로더 본인 또는 LEADER (기준안 #6)
        role = db.scalar(
            select(ProjectMember.role).where(
                ProjectMember.project_id == doc.project_id, ProjectMember.user_id == user.id
            )
        )
        if version.uploaded_by != user.id and role != MemberRole.LEADER:
            raise forbidden("업로더 또는 팀장만 버전을 삭제할 수 있습니다.")
    alive_count = db.scalar(select(func.count()).select_from(DocVersion).where(DocVersion.doc_id == doc.id))
    if alive_count <= 1:
        raise conflict(ErrorCode.LAST_VERSION_CANNOT_DELETE, "마지막 남은 버전은 삭제할 수 없습니다.")
    version.soft_delete()
    db.commit()
