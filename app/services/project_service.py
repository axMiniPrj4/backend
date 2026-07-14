"""프로젝트 cascade Soft Delete — LEADER 삭제와 관리자 삭제(기준안 #4)가 공유."""
import secrets
import string

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models import Doc, DocVersion, Project, ProjectTodo, Task

_CODE_ALPHABET = string.ascii_uppercase + string.digits
CODE_LENGTH = 8


def generate_unique_code(db: Session) -> str:
    while True:
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(CODE_LENGTH))
        exists = db.scalar(
            select(Project.id).where(Project.code == code).execution_options(include_deleted=True)
        )
        if not exists:
            return code


def cascade_delete_project(db: Session, project: Project) -> None:
    """project + task + doc + doc_version 동기 Soft Delete (Todo 제외, 단일 트랜잭션)."""
    now = utcnow()
    doc_ids = select(Doc.id).where(Doc.project_id == project.id)
    db.execute(
        update(DocVersion)
        .where(DocVersion.doc_id.in_(doc_ids), DocVersion.deleted_at.is_(None))
        .values(deleted_at=now)
    )
    db.execute(
        update(Doc).where(Doc.project_id == project.id, Doc.deleted_at.is_(None)).values(deleted_at=now)
    )
    db.execute(
        update(Task).where(Task.project_id == project.id, Task.deleted_at.is_(None)).values(deleted_at=now)
    )
    db.execute(
        update(ProjectTodo)
        .where(ProjectTodo.project_id == project.id, ProjectTodo.deleted_at.is_(None))
        .values(deleted_at=now)
    )
    project.deleted_at = now
    db.commit()
