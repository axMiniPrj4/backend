"""내 프로젝트 기준 최근 팀 활동 피드."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import (
    CalendarEvent,
    ChatMessage,
    Doc,
    Project,
    ProjectMember,
    Task,
    TaskComment,
    User,
)
from app.schemas.activity import ActivityItemOut

router = APIRouter(prefix="/api/activities", tags=["Activity"])


def _user_label(user: User | None, fallback_id: int | None = None) -> str:
    if user is None:
        return f"팀원 #{fallback_id}" if fallback_id else "알 수 없음"
    return user.nickname or user.name or user.login_id or f"팀원 #{user.id}"


def _trim(text: str | None, max_len: int = 40) -> str:
    if not text:
        return ""
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1] + "…"


@router.get("", response_model=list[ActivityItemOut])
def list_my_activities(
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    memberships = db.scalars(
        select(ProjectMember).where(ProjectMember.user_id == user.id)
    ).all()
    project_ids = [m.project_id for m in memberships]
    if not project_ids:
        return []

    projects = {
        p.id: p
        for p in db.scalars(select(Project).where(Project.id.in_(project_ids))).all()
        if not p.is_deleted
    }
    alive_ids = list(projects.keys())
    if not alive_ids:
        return []

    # 여유분 조회 후 병합·정렬
    per_source = max(limit, 10)

    chat_rows = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.project_id.in_(alive_ids))
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(per_source)
    ).all()

    task_rows = db.scalars(
        select(Task)
        .where(Task.project_id.in_(alive_ids))
        .options(selectinload(Task.creator))
        .order_by(Task.created_at.desc(), Task.id.desc())
        .limit(per_source)
    ).all()

    doc_rows = db.scalars(
        select(Doc)
        .where(Doc.project_id.in_(alive_ids))
        .options(selectinload(Doc.author))
        .order_by(Doc.created_at.desc(), Doc.id.desc())
        .limit(per_source)
    ).all()

    calendar_rows = db.scalars(
        select(CalendarEvent)
        .where(CalendarEvent.project_id.in_(alive_ids))
        .order_by(CalendarEvent.created_at.desc(), CalendarEvent.id.desc())
        .limit(per_source)
    ).all()

    comment_rows = db.scalars(
        select(TaskComment)
        .join(Task, Task.id == TaskComment.task_id)
        .where(Task.project_id.in_(alive_ids))
        .options(selectinload(TaskComment.author))
        .order_by(TaskComment.created_at.desc(), TaskComment.id.desc())
        .limit(per_source)
    ).all()

    author_ids = {m.author_id for m in chat_rows} | {e.created_by for e in calendar_rows}
    authors = {
        u.id: u
        for u in db.scalars(select(User).where(User.id.in_(author_ids))).all()
    } if author_ids else {}

    tasks_by_id = {t.id: t for t in task_rows}
    missing_task_ids = {c.task_id for c in comment_rows} - set(tasks_by_id)
    if missing_task_ids:
        for t in db.scalars(select(Task).where(Task.id.in_(missing_task_ids))).all():
            tasks_by_id[t.id] = t

    items: list[ActivityItemOut] = []

    for msg in chat_rows:
        project = projects.get(msg.project_id)
        if not project:
            continue
        author = authors.get(msg.author_id)
        if msg.type == "image":
            body = f"「{project.name}」에 이미지를 공유했습니다"
            icon = "image"
        elif msg.type == "emoji":
            body = f"「{project.name}」에서 이모지를 보냈습니다{(' ' + msg.content) if msg.content else ''}"
            icon = "mood"
        else:
            snippet = _trim(msg.content)
            body = (
                f"「{project.name}」에서 메시지를 보냈습니다"
                + (f": {snippet}" if snippet else "")
            )
            icon = "forum"
        items.append(
            ActivityItemOut(
                id=f"chat-{msg.id}",
                type="chat",
                user=_user_label(author, msg.author_id),
                user_id=msg.author_id,
                message=body,
                project_id=project.id,
                project_name=project.name,
                icon=icon,
                created_at=msg.created_at,
            )
        )

    for task in task_rows:
        project = projects.get(task.project_id)
        if not project:
            continue
        if task.status == "DONE":
            message = f"「{project.name}」작업 「{_trim(task.title, 28)}」을(를) 완료했습니다"
            icon = "task_alt"
        else:
            message = f"「{project.name}」에 작업 「{_trim(task.title, 28)}」을(를) 등록했습니다"
            icon = "add_task"
        items.append(
            ActivityItemOut(
                id=f"task-{task.id}",
                type="task",
                user=_user_label(task.creator, task.creator_id),
                user_id=task.creator_id,
                message=message,
                project_id=project.id,
                project_name=project.name,
                icon=icon,
                created_at=task.created_at,
            )
        )

    for doc in doc_rows:
        project = projects.get(doc.project_id) if doc.project_id else None
        if doc.project_id and not project:
            continue
        pname = project.name if project else "공통 자료실"
        items.append(
            ActivityItemOut(
                id=f"doc-{doc.id}",
                type="doc",
                user=_user_label(doc.author, doc.user_id),
                user_id=doc.user_id,
                message=f"「{pname}」에 자료 「{_trim(doc.title, 28)}」을(를) 올렸습니다",
                project_id=doc.project_id,
                project_name=pname,
                icon="upload_file",
                created_at=doc.created_at,
            )
        )

    for event in calendar_rows:
        project = projects.get(event.project_id)
        if not project:
            continue
        items.append(
            ActivityItemOut(
                id=f"calendar-{event.id}",
                type="calendar",
                user=_user_label(authors.get(event.created_by), event.created_by),
                user_id=event.created_by,
                message=f"「{project.name}」일정 「{_trim(event.title, 28)}」을(를) 등록했습니다",
                project_id=project.id,
                project_name=project.name,
                icon="event",
                created_at=event.created_at,
            )
        )

    for comment in comment_rows:
        task = tasks_by_id.get(comment.task_id)
        if not task:
            continue
        project = projects.get(task.project_id)
        if not project:
            continue
        items.append(
            ActivityItemOut(
                id=f"comment-{comment.id}",
                type="comment",
                user=_user_label(comment.author, comment.user_id),
                user_id=comment.user_id,
                message=(
                    f"「{project.name}」작업 「{_trim(task.title, 20)}」에 "
                    f"댓글을 남겼습니다: {_trim(comment.content, 32)}"
                ),
                project_id=project.id,
                project_name=project.name,
                icon="chat_bubble",
                created_at=comment.created_at,
            )
        )

    items.sort(key=lambda a: (a.created_at, a.id), reverse=True)
    return items[:limit]
