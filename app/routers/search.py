from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import bad_request
from app.db.session import get_db
from app.models import Doc, Project, ProjectMember, Task, User
from app.schemas.my_work import SearchHit, SearchResponse

router = APIRouter(prefix="/api/search", tags=["Search"])


@router.get("", response_model=SearchResponse)
def global_search(
    q: str = Query(..., min_length=1, max_length=80),
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = (q or "").strip()
    if not query:
        raise bad_request(message="검색어를 입력해주세요.")

    pattern = f"%{query}%"
    member_project_ids = list(
        db.scalars(select(ProjectMember.project_id).where(ProjectMember.user_id == user.id))
    )

    items: list[SearchHit] = []
    per = max(1, limit // 3)

    if member_project_ids:
        projects = db.scalars(
            select(Project)
            .where(Project.id.in_(member_project_ids), Project.name.ilike(pattern))
            .order_by(Project.updated_at.desc())
            .limit(per)
        ).all()
        for p in projects:
            items.append(
                SearchHit(
                    type="project",
                    id=p.id,
                    title=p.name,
                    subtitle=p.code,
                    link_url=f"/projects/{p.id}",
                )
            )

        tasks = db.scalars(
            select(Task)
            .where(Task.project_id.in_(member_project_ids), Task.title.ilike(pattern))
            .order_by(Task.updated_at.desc())
            .limit(per)
        ).all()
        project_names = {
            row.id: row.name
            for row in db.scalars(
                select(Project).where(Project.id.in_({t.project_id for t in tasks} or {-1}))
            )
        }
        for t in tasks:
            items.append(
                SearchHit(
                    type="task",
                    id=t.id,
                    title=t.title,
                    subtitle=project_names.get(t.project_id),
                    link_url=f"/projects/{t.project_id}?task={t.id}",
                )
            )

        docs = db.scalars(
            select(Doc)
            .where(
                Doc.title.ilike(pattern),
                or_(Doc.project_id.in_(member_project_ids), Doc.project_id.is_(None)),
            )
            .order_by(Doc.updated_at.desc())
            .limit(per)
        ).all()
    else:
        docs = db.scalars(
            select(Doc)
            .where(Doc.title.ilike(pattern), Doc.project_id.is_(None))
            .order_by(Doc.updated_at.desc())
            .limit(per)
        ).all()

    for d in docs:
        items.append(
            SearchHit(
                type="material",
                id=d.id,
                title=d.title,
                subtitle="공통 자료" if d.project_id is None else f"프로젝트 #{d.project_id}",
                link_url=f"/archive/{d.id}",
            )
        )

    return SearchResponse(items=items[:limit])
