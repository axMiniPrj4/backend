from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import ProjectContext, get_project_context
from app.core.errors import bad_request, forbidden, not_found
from app.db.session import get_db
from app.models import ProjectTodo, Task
from app.models.task import TaskPriority
from app.models.todo import TodoStatus
from app.schemas.task import TaskResponse
from app.schemas.todo import ProjectTodoCreateRequest, ProjectTodoResponse, ProjectTodoUpdateRequest
from app.services.task_history import add_task_history

router = APIRouter(prefix="/api/projects/{project_id}/todos", tags=["ProjectTodo"])


def _get_project_todo(db: Session, ctx: ProjectContext, todo_id: int) -> ProjectTodo:
    todo = db.scalar(
        select(ProjectTodo)
        .where(ProjectTodo.id == todo_id, ProjectTodo.project_id == ctx.project.id)
        .options(selectinload(ProjectTodo.author))
    )
    if todo is None:
        raise not_found("프로젝트 체크리스트를 찾을 수 없습니다.")
    return todo


@router.post("", response_model=ProjectTodoResponse, status_code=201)
def create_project_todo(
    body: ProjectTodoCreateRequest,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    todo = ProjectTodo(
        project_id=ctx.project.id, user_id=ctx.user.id, content=body.content, priority=body.priority
    )
    db.add(todo)
    db.commit()
    return _get_project_todo(db, ctx, todo.id)


@router.get("", response_model=list[ProjectTodoResponse])
def list_project_todos(
    status: str | None = Query(None),
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    allowed = {TodoStatus.DONE, TodoStatus.NOT_DONE}
    if status is not None and status not in allowed:
        raise bad_request(message=f"status 필터는 {sorted(allowed)} 중 하나여야 합니다.")
    stmt = (
        select(ProjectTodo)
        .where(ProjectTodo.project_id == ctx.project.id)
        .options(selectinload(ProjectTodo.author))
        .order_by(ProjectTodo.created_at.desc(), ProjectTodo.id.desc())
    )
    if status is not None:
        stmt = stmt.where(ProjectTodo.status == status)
    return list(db.scalars(stmt))


@router.patch("/{todo_id}", response_model=ProjectTodoResponse)
def update_project_todo(
    todo_id: int,
    body: ProjectTodoUpdateRequest,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    todo = _get_project_todo(db, ctx, todo_id)
    if not (ctx.is_leader or todo.user_id == ctx.user.id):
        raise forbidden("작성자 또는 팀장만 수정할 수 있습니다.")
    data = body.model_dump(exclude_unset=True)
    if data.get("status") is not None and data["status"] not in {TodoStatus.DONE, TodoStatus.NOT_DONE}:
        raise bad_request(message="체크리스트 상태는 DONE 또는 NOT_DONE만 가능합니다.")
    for field, value in data.items():
        if value is not None:
            setattr(todo, field, value)
    db.commit()
    return todo


@router.post("/{todo_id}/promote", response_model=TaskResponse, status_code=201)
def promote_project_todo_to_task(
    todo_id: int,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    """체크리스트 항목을 프로젝트 Task로 승격하고 체크리스트는 완료 처리."""
    todo = _get_project_todo(db, ctx, todo_id)
    today = date.today()
    start = ctx.project.start_date or today
    end = ctx.project.end_date or (today + timedelta(days=7))
    if start > end:
        start, end = end, start
    if today < start:
        t_start = start
    elif today > end:
        t_start = end
    else:
        t_start = today
    t_end = end if end >= t_start else t_start
    priority = todo.priority if todo.priority in TaskPriority.ALL else TaskPriority.MEDIUM
    task = Task(
        project_id=ctx.project.id,
        title=todo.content[:200],
        content=None,
        creator_id=ctx.user.id,
        start_date=t_start,
        end_date=t_end,
        assignees=[ctx.user],
        priority=priority,
        category="기타",
        work_group="",
    )
    db.add(task)
    db.flush()
    add_task_history(
        db,
        task=task,
        actor_id=ctx.user.id,
        event_type="PROMOTED",
        message=f"{ctx.user.nickname}님이 체크리스트에서 작업으로 승격했습니다.",
    )
    todo.status = TodoStatus.DONE
    db.commit()
    return db.scalar(select(Task).where(Task.id == task.id).options(selectinload(Task.assignees)))


@router.delete("/{todo_id}", status_code=204)
def delete_project_todo(
    todo_id: int,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    todo = _get_project_todo(db, ctx, todo_id)
    if not (ctx.is_leader or todo.user_id == ctx.user.id):
        raise forbidden("작성자 또는 팀장만 삭제할 수 있습니다.")
    todo.soft_delete()
    db.commit()
