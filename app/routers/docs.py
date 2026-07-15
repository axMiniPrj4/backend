from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import ProjectContext, get_project_context
from app.core.errors import ErrorCode, conflict, forbidden, not_found
from app.core.files import delete_stored_file, save_upload, stream_download
from app.core.pagination import DEFAULT_SIZE, parse_page_params, paginate
from app.db.base import utcnow
from app.db.session import get_db
from app.models import Doc, DocVersion
from app.schemas.common import PageResponse
from app.schemas.doc import DocResponse, DocUpdateRequest, DocVersionResponse

router = APIRouter(prefix="/api/projects/{project_id}/docs", tags=["Doc"])

_SORT_FIELDS = {"created_at", "title"}
_SUBDIR = "docs"


def _latest_version(doc: Doc) -> DocVersion | None:
    alive = [v for v in doc.versions if not v.is_deleted]
    return max(alive, key=lambda v: v.version_no) if alive else None


def _to_response(doc: Doc) -> DocResponse:
    latest = _latest_version(doc)
    return DocResponse(
        id=doc.id,
        project_id=doc.project_id,
        user_id=doc.user_id,
        title=doc.title,
        content=doc.content,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        latest_version=DocVersionResponse.model_validate(latest) if latest else None,
    )


def _get_doc(db: Session, ctx: ProjectContext, doc_id: int) -> Doc:
    doc = db.scalar(
        select(Doc)
        .where(Doc.id == doc_id, Doc.project_id == ctx.project.id)
        .options(selectinload(Doc.versions))
    )
    if doc is None:
        raise not_found("자료를 찾을 수 없습니다.")
    return doc


def _require_author_or_leader(ctx: ProjectContext, doc: Doc, action: str):
    if not (ctx.is_leader or doc.user_id == ctx.user.id):
        raise forbidden(f"작성자 또는 팀장만 {action}할 수 있습니다.")


@router.post("", response_model=DocResponse, status_code=201)
def create_doc(
    title: str = Form(min_length=1, max_length=200),
    content: str | None = Form(None),
    file: UploadFile = File(...),  # 등록 시 파일 필수 → version 1 자동 생성
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    stored = save_upload(file, _SUBDIR)
    try:
        # 단일 트랜잭션: doc INSERT + doc_version(v1) INSERT (실패 시 파일 롤백)
        doc = Doc(project_id=ctx.project.id, user_id=ctx.user.id, title=title, content=content)
        db.add(doc)
        db.flush()
        version = DocVersion(
            doc_id=doc.id,
            version_no=1,
            file_name=stored.file_name,
            stored_name=stored.stored_name,
            file_size=stored.file_size,
            mime_type=stored.mime_type,
            uploaded_by=ctx.user.id,
        )
        db.add(version)
        db.commit()
    except Exception:
        db.rollback()
        delete_stored_file(stored.stored_name)
        raise
    return _to_response(_get_doc(db, ctx, doc.id))


@router.get("", response_model=PageResponse[DocResponse])
def list_docs(
    page: int = Query(1),
    size: int = Query(DEFAULT_SIZE),
    sort: str | None = Query(None),
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    params = parse_page_params(page, size, sort, _SORT_FIELDS)
    stmt = select(Doc).where(Doc.project_id == ctx.project.id).options(selectinload(Doc.versions))
    page_data = paginate(db, stmt, Doc, params)
    page_data["items"] = [_to_response(d) for d in page_data["items"]]
    return page_data


@router.get("/{doc_id}", response_model=DocResponse)
def get_doc(doc_id: int, ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    return _to_response(_get_doc(db, ctx, doc_id))


@router.get("/{doc_id}/file")
def download_latest(doc_id: int, ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    doc = _get_doc(db, ctx, doc_id)
    latest = _latest_version(doc)
    if latest is None:
        raise not_found("다운로드할 파일이 없습니다.")
    return stream_download(latest.stored_name, latest.file_name, latest.mime_type)


@router.patch("/{doc_id}", response_model=DocResponse)
def update_doc(
    doc_id: int,
    body: DocUpdateRequest,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    doc = _get_doc(db, ctx, doc_id)
    _require_author_or_leader(ctx, doc, "수정")
    data = body.model_dump(exclude_unset=True)
    # 프로젝트 스코프 API에서는 소속 이동 불가 (전역 /archive PATCH 사용)
    data.pop("project_id", None)
    for field, value in data.items():
        setattr(doc, field, value)
    db.commit()
    return _to_response(doc)


@router.delete("/{doc_id}", status_code=204)
def delete_doc(doc_id: int, ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    doc = _get_doc(db, ctx, doc_id)
    _require_author_or_leader(ctx, doc, "삭제")
    # 게시글 + 하위 버전 전체 Soft Delete (물리 파일은 보관)
    now = utcnow()
    for v in doc.versions:
        if not v.is_deleted:
            v.deleted_at = now
    doc.deleted_at = now
    db.commit()


# ---------- 버전 관리 ----------


@router.post("/{doc_id}/versions", response_model=DocVersionResponse, status_code=201)
def upload_version(
    doc_id: int,
    file: UploadFile = File(...),
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    """새 버전 업로드 — 프로젝트 멤버 누구나. version_no = 현재 MAX + 1 (삭제 버전 포함)."""
    doc = _get_doc(db, ctx, doc_id)
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
            uploaded_by=ctx.user.id,
        )
        db.add(version)
        db.commit()
    except Exception:
        db.rollback()
        delete_stored_file(stored.stored_name)
        raise
    return version


@router.get("/{doc_id}/versions", response_model=list[DocVersionResponse])
def list_versions(doc_id: int, ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    doc = _get_doc(db, ctx, doc_id)
    versions = db.scalars(
        select(DocVersion).where(DocVersion.doc_id == doc.id).order_by(DocVersion.version_no.desc())
    ).all()
    return versions


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
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    doc = _get_doc(db, ctx, doc_id)
    version = _get_version(db, doc, version_no)
    return stream_download(version.stored_name, version.file_name, version.mime_type)


@router.delete("/{doc_id}/versions/{version_no}", status_code=204)
def delete_version(
    doc_id: int,
    version_no: int,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    doc = _get_doc(db, ctx, doc_id)
    version = _get_version(db, doc, version_no)
    # 기준안 #6: 업로더 본인 또는 LEADER
    if not (ctx.is_leader or version.uploaded_by == ctx.user.id):
        raise forbidden("업로더 또는 팀장만 버전을 삭제할 수 있습니다.")
    alive_count = db.scalar(
        select(func.count()).select_from(DocVersion).where(DocVersion.doc_id == doc.id)
    )
    # 기준안 #7: 마지막 남은 버전은 삭제 불가 — 파일 필수 정책 유지
    if alive_count <= 1:
        raise conflict(ErrorCode.LAST_VERSION_CANNOT_DELETE, "마지막 남은 버전은 삭제할 수 없습니다.")
    version.soft_delete()
    db.commit()
