"""인앱 알림 생성 헬퍼 — 본인 액션은 수신자에서 제외."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.notification import Notification, NotificationType
from app.models.task import Task, TaskStatus


STATUS_LABEL = {
    TaskStatus.TODO: "할 일",
    TaskStatus.IN_PROGRESS: "진행 중",
    TaskStatus.DONE: "완료",
}


def task_link(project_id: int, task_id: int) -> str:
    return f"/projects/{project_id}?task={task_id}"


def notify_users(
    db: Session,
    *,
    user_ids: set[int] | list[int],
    actor_id: int | None,
    type: str,
    title: str,
    body: str | None = None,
    link_url: str | None = None,
    project_id: int | None = None,
    task_id: int | None = None,
) -> int:
    """알림 행 추가 (flush만, commit은 호출측). 반환: 생성 건수."""
    created = 0
    for uid in dict.fromkeys(user_ids):
        if uid is None:
            continue
        if actor_id is not None and uid == actor_id:
            continue
        db.add(
            Notification(
                user_id=uid,
                actor_id=actor_id,
                type=type,
                title=title,
                body=body,
                link_url=link_url,
                project_id=project_id,
                task_id=task_id,
            )
        )
        created += 1
    return created


def notify_task_assigned(
    db: Session,
    *,
    task: Task,
    actor_id: int,
    actor_nickname: str,
    new_assignee_ids: list[int],
) -> None:
    if not new_assignee_ids:
        return
    notify_users(
        db,
        user_ids=new_assignee_ids,
        actor_id=actor_id,
        type=NotificationType.TASK_ASSIGNED,
        title="작업 담당자로 지정되었습니다",
        body=f"{actor_nickname}님이 「{task.title}」에 나를 담당자로 지정했습니다.",
        link_url=task_link(task.project_id, task.id),
        project_id=task.project_id,
        task_id=task.id,
    )


def notify_task_status(
    db: Session,
    *,
    task: Task,
    actor_id: int,
    actor_nickname: str,
    new_status: str,
) -> None:
    recipients = set(task.assignee_ids)
    recipients.add(task.creator_id)
    label = STATUS_LABEL.get(new_status, new_status)
    notify_users(
        db,
        user_ids=recipients,
        actor_id=actor_id,
        type=NotificationType.TASK_STATUS,
        title="작업 상태가 변경되었습니다",
        body=f"{actor_nickname}님이 「{task.title}」 상태를 {label}(으)로 변경했습니다.",
        link_url=task_link(task.project_id, task.id),
        project_id=task.project_id,
        task_id=task.id,
    )


def notify_task_comment(
    db: Session,
    *,
    task: Task,
    actor_id: int,
    actor_nickname: str,
    comment_preview: str,
) -> None:
    recipients = set(task.assignee_ids)
    recipients.add(task.creator_id)
    preview = (comment_preview or "").strip()
    if len(preview) > 80:
        preview = preview[:77] + "..."
    notify_users(
        db,
        user_ids=recipients,
        actor_id=actor_id,
        type=NotificationType.TASK_COMMENT,
        title="작업에 새 댓글이 달렸습니다",
        body=f"{actor_nickname}님: {preview}" if preview else f"{actor_nickname}님이 댓글을 남겼습니다.",
        link_url=task_link(task.project_id, task.id),
        project_id=task.project_id,
        task_id=task.id,
    )
