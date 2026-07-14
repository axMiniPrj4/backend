from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import ProjectContext, get_project_context
from app.core.errors import bad_request, forbidden, not_found
from app.db.session import get_db
from app.models import ProjectTodo
from app.models.todo import TodoStatus
from app.schemas.todo import ProjectTodoCreateRequest, ProjectTodoResponse, ProjectTodoUpdateRequest

router = APIRouter(prefix="/api/projects/{project_id}/todos", tags=["ProjectTodo"])


def _get_project_todo(db: Session, ctx: ProjectContext, todo_id: int) -> ProjectTodo:
    todo = db.scalar(
        select(ProjectTodo)
        .where(ProjectTodo.id == todo_id, ProjectTodo.project_id == ctx.project.id)
        .options(selectinload(ProjectTodo.author))
    )
    if todo is None:
        raise not_found("프로젝트 할 일을 찾을 수 없습니다.")
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
    if status is not None and status not in TodoStatus.ALL:
        raise bad_request(message=f"status 필터는 {sorted(TodoStatus.ALL)} 중 하나여야 합니다.")
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
    # ④ 리소스 소유권: 작성자 또는 LEADER
    if not (ctx.is_leader or todo.user_id == ctx.user.id):
        raise forbidden("작성자 또는 팀장만 수정할 수 있습니다.")
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        if value is not None:
            setattr(todo, field, value)
    db.commit()
    return todo


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
