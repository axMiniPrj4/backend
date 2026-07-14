from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import bad_request, not_found
from app.core.pagination import DEFAULT_SIZE, MAX_SIZE
from app.db.session import get_db
from app.models import Notice, User
from app.models.notice import NoticeCategory
from app.schemas.common import PageResponse
from app.schemas.notice import NoticeResponse

router = APIRouter(prefix="/api/notices", tags=["Notice"])


@router.get("", response_model=PageResponse[NoticeResponse])
def list_notices(
    category: str | None = Query(None),
    page: int = Query(1),
    size: int = Query(DEFAULT_SIZE),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """공지 목록 — 고정(pinned) 우선 + 최신순 고정 정렬 (sort 파라미터 없음)."""
    if page < 1 or size < 1 or size > MAX_SIZE:
        raise bad_request(message=f"page는 1 이상, size는 1~{MAX_SIZE} 사이여야 합니다.")
    if category is not None and category not in NoticeCategory.ALL:
        raise bad_request(message=f"category 필터는 {sorted(NoticeCategory.ALL)} 중 하나여야 합니다.")

    filters = [Notice.deleted_at.is_(None)]
    if category is not None:
        filters.append(Notice.category == category)
    total = db.scalar(select(func.count()).select_from(Notice).where(*filters)) or 0
    items = list(
        db.scalars(
            select(Notice)
            .where(*filters)
            .order_by(Notice.pinned.desc(), Notice.created_at.desc(), Notice.id.desc())
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


@router.get("/{notice_id}", response_model=NoticeResponse)
def get_notice(notice_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    notice = db.scalar(select(Notice).where(Notice.id == notice_id))
    if notice is None:
        raise not_found("공지사항을 찾을 수 없습니다.")
    return notice
