"""페이지네이션 공통 — ?page=1&size=20&sort=created_at,desc (size 최대 100, 허용 외 정렬 400)."""
from dataclasses import dataclass

from sqlalchemy import Select, func
from sqlalchemy.orm import Session

from app.core.errors import bad_request
from app.db.base import SoftDeleteMixin

MAX_SIZE = 100
DEFAULT_SIZE = 10
DEFAULT_SORT = "created_at,desc"


@dataclass
class PageParams:
    page: int
    size: int
    sort_field: str
    sort_desc: bool


def parse_page_params(page: int, size: int, sort: str | None, allowed_sort_fields: set[str]) -> PageParams:
    if page < 1:
        raise bad_request(message="page는 1 이상이어야 합니다.")
    if size < 1 or size > MAX_SIZE:
        raise bad_request(message=f"size는 1~{MAX_SIZE} 사이여야 합니다.")
    raw = sort or DEFAULT_SORT
    parts = raw.split(",")
    field = parts[0].strip()
    direction = parts[1].strip().lower() if len(parts) > 1 else "asc"
    if field not in allowed_sort_fields:
        raise bad_request(message=f"허용되지 않는 정렬 필드입니다: {field}")
    if direction not in ("asc", "desc"):
        raise bad_request(message=f"정렬 방향은 asc/desc만 허용됩니다: {direction}")
    return PageParams(page=page, size=size, sort_field=field, sort_desc=direction == "desc")


def paginate(db: Session, stmt: Select, model, params: PageParams) -> dict:
    """정렬·페이징 적용 후 공통 응답 dict 반환. items는 ORM 객체 리스트."""
    # 카운트 쿼리는 엔티티 컬럼이 빠져 soft delete 자동 필터가 적용되지 않으므로 명시적으로 필터
    if issubclass(model, SoftDeleteMixin):
        stmt = stmt.where(model.deleted_at.is_(None))
    total = db.scalar(stmt.with_only_columns(func.count()).order_by(None)) or 0
    col = getattr(model, params.sort_field)
    stmt = stmt.order_by(col.desc() if params.sort_desc else col.asc(), model.id.desc())
    stmt = stmt.offset((params.page - 1) * params.size).limit(params.size)
    items = list(db.scalars(stmt))
    return {
        "items": items,
        "page": params.page,
        "size": params.size,
        "total_elements": total,
        "total_pages": (total + params.size - 1) // params.size,
    }
