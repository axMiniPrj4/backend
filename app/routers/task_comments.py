from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import ProjectContext, get_project_context
from app.core.errors import forbidden, not_found
from app.db.session import get_db
from app.models import Task, TaskComment
from app.schemas.task import TaskCommentCreateRequest, TaskCommentResponse

router = APIRouter(prefix="/api/projects/{project_id}/tasks/{task_id}/comments", tags=["TaskComment"])


def _ensure_task(db: Session, ctx: ProjectContext, task_id: int) -> Task:
    task = db.scalar(select(Task).where(Task.id == task_id, Task.project_id == ctx.project.id))
    if task is None:
        raise not_found("업무를 찾을 수 없습니다.")
    return task


def _get_comment(db: Session, task: Task, comment_id: int) -> TaskComment:
    comment = db.scalar(
        select(TaskComment)
        .where(TaskComment.id == comment_id, TaskComment.task_id == task.id)
        .options(selectinload(TaskComment.author), selectinload(TaskComment.likers))
    )
    if comment is None:
        raise not_found("댓글을 찾을 수 없습니다.")
    return comment


def _to_response(comment: TaskComment, user_id: int) -> TaskCommentResponse:
    resp = TaskCommentResponse.model_validate(comment)
    resp.liked_by_me = any(u.id == user_id for u in comment.likers)
    return resp


@router.post("", response_model=TaskCommentResponse, status_code=201)
def create_comment(
    task_id: int,
    body: TaskCommentCreateRequest,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    task = _ensure_task(db, ctx, task_id)
    comment = TaskComment(task_id=task.id, user_id=ctx.user.id, content=body.content)
    db.add(comment)
    db.commit()
    return _to_response(_get_comment(db, task, comment.id), ctx.user.id)


@router.get("", response_model=list[TaskCommentResponse])
def list_comments(
    task_id: int,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    task = _ensure_task(db, ctx, task_id)
    comments = db.scalars(
        select(TaskComment)
        .where(TaskComment.task_id == task.id)
        .options(selectinload(TaskComment.author), selectinload(TaskComment.likers))
        .order_by(TaskComment.created_at.asc(), TaskComment.id.asc())
    ).all()
    return [_to_response(c, ctx.user.id) for c in comments]


@router.delete("/{comment_id}", status_code=204)
def delete_comment(
    task_id: int,
    comment_id: int,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    task = _ensure_task(db, ctx, task_id)
    comment = _get_comment(db, task, comment_id)
    # ④ 리소스 소유권: 작성자 또는 LEADER
    if not (ctx.is_leader or comment.user_id == ctx.user.id):
        raise forbidden("작성자 또는 팀장만 삭제할 수 있습니다.")
    comment.soft_delete()
    db.commit()


@router.post("/{comment_id}/like", response_model=TaskCommentResponse)
def like_comment(
    task_id: int,
    comment_id: int,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    """좋아요 등록 — 이미 눌렀으면 변화 없음 (멱등)."""
    task = _ensure_task(db, ctx, task_id)
    comment = _get_comment(db, task, comment_id)
    if all(u.id != ctx.user.id for u in comment.likers):
        comment.likers.append(ctx.user)
        db.commit()
    return _to_response(comment, ctx.user.id)


@router.delete("/{comment_id}/like", response_model=TaskCommentResponse)
def unlike_comment(
    task_id: int,
    comment_id: int,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    """좋아요 취소 — 누르지 않았으면 변화 없음 (멱등)."""
    task = _ensure_task(db, ctx, task_id)
    comment = _get_comment(db, task, comment_id)
    target = next((u for u in comment.likers if u.id == ctx.user.id), None)
    if target is not None:
        comment.likers.remove(target)
        db.commit()
    return _to_response(comment, ctx.user.id)
