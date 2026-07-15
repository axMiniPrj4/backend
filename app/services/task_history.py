"""Task 변경 히스토리 기록."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.task import Task, TaskHistory


def add_task_history(
    db: Session,
    *,
    task: Task,
    actor_id: int,
    event_type: str,
    message: str,
) -> None:
    db.add(
        TaskHistory(
            task_id=task.id,
            project_id=task.project_id,
            actor_id=actor_id,
            event_type=event_type,
            message=message[:500],
        )
    )
