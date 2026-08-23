from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
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


def _next_sort_order(db: Session, project_id: int, parent_id: int | None) -> int:
    max_order = db.scalar(
        select(func.max(ProjectTodo.sort_order)).where(
            ProjectTodo.project_id == project_id, ProjectTodo.parent_id == parent_id
        )
    )
    return (max_order or 0) + 1


def _resolve_parent(db: Session, ctx: ProjectContext, parent_id: int | None, *, exclude_id: int | None = None) -> None:
    """parent_id가 같은 프로젝트에 속하고, 자기 자신/자손을 부모로 삼지 않는지 검증."""
    if parent_id is None:
        return
    parent = db.scalar(select(ProjectTodo).where(ProjectTodo.id == parent_id, ProjectTodo.project_id == ctx.project.id))
    if parent is None:
        raise bad_request(message="상위 체크리스트를 찾을 수 없습니다.")
    if exclude_id is None:
        return
    node = parent
    while node is not None:
        if node.id == exclude_id:
            raise bad_request(message="체크리스트를 자기 자신 또는 하위 항목의 하위로 옮길 수 없습니다.")
        node = node.parent


@router.post("", response_model=ProjectTodoResponse, status_code=201)
def create_project_todo(
    body: ProjectTodoCreateRequest,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    _resolve_parent(db, ctx, body.parent_id)
    todo = ProjectTodo(
        project_id=ctx.project.id,
        user_id=ctx.user.id,
        content=body.content,
        priority=body.priority,
        parent_id=body.parent_id,
        sort_order=_next_sort_order(db, ctx.project.id, body.parent_id),
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
        .order_by(ProjectTodo.sort_order.asc(), ProjectTodo.id.asc())
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
    if "parent_id" in data:
        new_parent_id = data.pop("parent_id")
        _resolve_parent(db, ctx, new_parent_id, exclude_id=todo.id)
        todo.parent_id = new_parent_id
        todo.sort_order = _next_sort_order(db, ctx.project.id, new_parent_id)
    if "sort_order" in data:
        todo.sort_order = data.pop("sort_order")
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
    stack = [todo]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        node.soft_delete()
    db.commit()
