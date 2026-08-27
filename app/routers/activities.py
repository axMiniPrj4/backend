"""내 프로젝트 기준 최근 팀 활동 피드.

소스: task_history(작업 이벤트) · task(이력 없는 레거시 작업 보완) · opr_report ·
      doc · chat_message · calendar_event · task_comment

설계 메모
- 권한 기준은 projects.list_my_projects 와 동일하게 맞춘다(SYSTEM_ADMIN 은 전체 열람).
  예전에는 project_member 행만 봤기 때문에, 관리자가 열 수 있어도 멤버가 아닌
  프로젝트는 최근 활동이 영구히 빈 칸이었다.
- project_id 를 주면 서버에서 좁힌다. 예전에는 전역 최신 N건만 내려주고 프론트가
  걸러내서, 참여 프로젝트가 늘면 특정 프로젝트가 0건이 되곤 했다.
- 작업 활동은 task_history 를 우선 사용한다. task 행에서 역산하던 방식은 상태를
  완료로 바꾸면 '등록' 기록이 '완료'로 덮여 사라지고 시각도 생성 시각으로 남았다.
  단 이력이 없는 과거 작업(엑셀 일괄 등록 등)은 task 행으로 보완하며,
  중복은 CREATED 이력 유무로 걸러낸다.
- soft delete 된 행은 db/base.py 의 _soft_delete_filter 가 ORM 조회에서 자동 제외한다.
"""
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import (
    CalendarEvent,
    ChatMessage,
    Doc,
    OprReport,
    Project,
    ProjectMember,
    Task,
    TaskComment,
    TaskHistory,
    User,
)
from app.models.user import UserRole
from app.schemas.activity import ActivityItemOut

router = APIRouter(prefix="/api/activities", tags=["Activity"])

# task_history.event_type -> 아이콘
_HISTORY_ICON = {
    "CREATED": "add_task",
    "STATUS": "task_alt",
    "ASSIGNED": "person_add",
    "UNASSIGNED": "person_remove",
    "PRIORITY": "flag",
}

# opr_report.status -> 표시 동사
_OPR_VERB = {
    "DRAFT": "작성했습니다",
    "SHARED": "공유했습니다",
    "CONFIRMED": "확정했습니다",
}


def _user_label(user: User | None, fallback_id: int | None = None) -> str:
    # 실명 우선 — 화면 전반에서 닉네임보다 이름으로 표기한다
    if user is None:
        return f"팀원 #{fallback_id}" if fallback_id else "알 수 없음"
    return user.name or user.nickname or user.login_id or f"팀원 #{user.id}"


def _trim(text: str | None, max_len: int = 40) -> str:
    if not text:
        return ""
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1] + "…"


def _strip_actor_prefix(message: str, actor_label: str) -> str:
    """task_history.message 는 '홍길동님이 …' 형태로 저장된다.

    화면이 '{user} 님이' 를 앞에 붙이므로 그대로 쓰면 이름이 두 번 나온다.
    """
    text = " ".join((message or "").split())
    if actor_label:
        for prefix in (f"{actor_label}님이 ", f"{actor_label} 님이 "):
            if text.startswith(prefix):
                return text[len(prefix) :]
    # 표시명이 바뀐 뒤 쌓인 기록도 처리 — 앞쪽 '님이 ' 까지 잘라낸다
    marker = "님이 "
    idx = text.find(marker)
    if 0 < idx <= 30:
        return text[idx + len(marker) :]
    return text


def _visible_projects(db: Session, user: User, project_id: int | None) -> dict[int, Project]:
    """활동을 노출할 프로젝트 — 프로젝트 목록 조회 권한과 같은 기준."""
    if user.role == UserRole.SYSTEM_ADMIN:
        stmt = select(Project)
    else:
        stmt = (
            select(Project)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(ProjectMember.user_id == user.id)
        )
    if project_id is not None:
        stmt = stmt.where(Project.id == project_id)
    return {p.id: p for p in db.scalars(stmt).all() if not p.is_deleted}


@router.get("", response_model=list[ActivityItemOut])
def list_my_activities(
    limit: int = Query(20, ge=1, le=50),
    project_id: int | None = Query(None, description="지정하면 해당 프로젝트 활동만 내려준다"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    projects = _visible_projects(db, user, project_id)
    if not projects:
        # 권한이 없거나 볼 프로젝트가 없는 경우 — 빈 피드
        return []
    alive_ids = list(projects.keys())

    # 소스별로 여유분을 뽑아 병합·정렬한다.
    # project_id 가 주어졌다면 alive_ids 가 그 프로젝트 하나라서 아래 조회가 모두 좁혀진다.
    per_source = max(limit, 10)

    items: list[ActivityItemOut] = []

    # ── 작업 이벤트: task_history 우선 ───────────────────────────────
    history_rows = db.scalars(
        select(TaskHistory)
        .where(TaskHistory.project_id.in_(alive_ids))
        .options(selectinload(TaskHistory.actor))
        .order_by(TaskHistory.created_at.desc(), TaskHistory.id.desc())
        .limit(per_source)
    ).all()

    history_task_ids = {h.task_id for h in history_rows}
    # ORM 조회이므로 삭제된 작업은 자동으로 빠진다 → 조회되지 않은 id 는 건너뛴다
    history_tasks = (
        {t.id: t for t in db.scalars(select(Task).where(Task.id.in_(history_task_ids))).all()}
        if history_task_ids
        else {}
    )

    for h in history_rows:
        project = projects.get(h.project_id)
        task = history_tasks.get(h.task_id)
        if not project or task is None:
            continue
        actor_label = _user_label(h.actor, h.actor_id)
        title = _trim(task.title, 28)
        if h.event_type == "CREATED":
            message = f"「{project.name}」에 작업 「{title}」을(를) 등록했습니다"
        else:
            verb = _strip_actor_prefix(h.message, actor_label)
            message = (
                f"「{project.name}」작업 「{title}」의 {verb}"
                if verb
                else f"「{project.name}」작업 「{title}」을(를) 수정했습니다"
            )
        items.append(
            ActivityItemOut(
                id=f"history-{h.id}",
                type="task",
                user=actor_label,
                user_id=h.actor_id,
                message=message,
                project_id=project.id,
                project_name=project.name,
                icon=_HISTORY_ICON.get(h.event_type, "history"),
                created_at=h.created_at,
            )
        )

    # ── 이력이 없는 과거 작업 보완 (WBS 엑셀 일괄 등록 등) ──────────
    task_rows = db.scalars(
        select(Task)
        .where(Task.project_id.in_(alive_ids))
        .options(selectinload(Task.creator))
        .order_by(Task.created_at.desc(), Task.id.desc())
        .limit(per_source)
    ).all()
    candidate_ids = [t.id for t in task_rows]
    logged_ids = (
        set(
            db.scalars(
                select(TaskHistory.task_id).where(
                    TaskHistory.task_id.in_(candidate_ids),
                    TaskHistory.event_type == "CREATED",
                )
            ).all()
        )
        if candidate_ids
        else set()
    )
    for task in task_rows:
        project = projects.get(task.project_id)
        if not project or task.id in logged_ids:
            continue
        items.append(
            ActivityItemOut(
                id=f"task-{task.id}",
                type="task",
                user=_user_label(task.creator, task.creator_id),
                user_id=task.creator_id,
                message=f"「{project.name}」에 작업 「{_trim(task.title, 28)}」을(를) 등록했습니다",
                project_id=project.id,
                project_name=project.name,
                icon="add_task",
                created_at=task.created_at,
            )
        )

    # ── OPR ─────────────────────────────────────────────────────────
    opr_reports = db.scalars(
        select(OprReport)
        .where(OprReport.project_id.in_(alive_ids))
        .options(selectinload(OprReport.author))
        .order_by(OprReport.created_at.desc(), OprReport.id.desc())
        .limit(per_source)
    ).all()
    for report in opr_reports:
        project = projects.get(report.project_id)
        if not project:
            continue
        day = ""
        if isinstance(report.report_date, date):
            day = f"{report.report_date.month}/{report.report_date.day} "
        items.append(
            ActivityItemOut(
                id=f"opr-{report.id}",
                type="opr",
                user=_user_label(report.author, report.author_id),
                user_id=report.author_id,
                message=f"「{project.name}」{day}OPR을 {_OPR_VERB.get(report.status, '작성했습니다')}",
                project_id=project.id,
                project_name=project.name,
                icon="assignment",
                created_at=report.created_at,
            )
        )

    # ── 자료실 ──────────────────────────────────────────────────────
    doc_stmt = select(Doc).options(selectinload(Doc.author))
    if project_id is not None:
        doc_stmt = doc_stmt.where(Doc.project_id == project_id)
    else:
        # project_id IS NULL 은 공통 자료실 — IN 절은 NULL 을 잡지 못해 따로 포함시킨다
        doc_stmt = doc_stmt.where(or_(Doc.project_id.in_(alive_ids), Doc.project_id.is_(None)))
    for doc in db.scalars(
        doc_stmt.order_by(Doc.created_at.desc(), Doc.id.desc()).limit(per_source)
    ).all():
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

    # ── 채팅 / 일정 ─────────────────────────────────────────────────
    chat_rows = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.project_id.in_(alive_ids))
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(per_source)
    ).all()
    calendar_rows = db.scalars(
        select(CalendarEvent)
        .where(CalendarEvent.project_id.in_(alive_ids))
        .order_by(CalendarEvent.created_at.desc(), CalendarEvent.id.desc())
        .limit(per_source)
    ).all()
    author_ids = {m.author_id for m in chat_rows} | {e.created_by for e in calendar_rows}
    authors = (
        {u.id: u for u in db.scalars(select(User).where(User.id.in_(author_ids))).all()}
        if author_ids
        else {}
    )

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
            body = f"「{project.name}」에서 메시지를 보냈습니다" + (f": {snippet}" if snippet else "")
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

    # ── 작업 댓글 ───────────────────────────────────────────────────
    comment_rows = db.scalars(
        select(TaskComment)
        .join(Task, Task.id == TaskComment.task_id)
        .where(Task.project_id.in_(alive_ids))
        .options(selectinload(TaskComment.author))
        .order_by(TaskComment.created_at.desc(), TaskComment.id.desc())
        .limit(per_source)
    ).all()
    comment_task_ids = {c.task_id for c in comment_rows}
    comment_tasks = (
        {t.id: t for t in db.scalars(select(Task).where(Task.id.in_(comment_task_ids))).all()}
        if comment_task_ids
        else {}
    )
    for comment in comment_rows:
        task = comment_tasks.get(comment.task_id)
        if task is None:
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

