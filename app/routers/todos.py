from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import bad_request, not_found
from app.db.session import get_db
from app.models import Todo, User
from app.models.todo import TodoStatus
from app.schemas.todo import TodoCreateRequest, TodoResponse, TodoUpdateRequest

router = APIRouter(prefix="/api/todos", tags=["Todo"])


def _get_my_todo(db: Session, user: User, todo_id: int) -> Todo:
    todo = db.scalar(select(Todo).where(Todo.id == todo_id))
    # 타인의 개인 리소스 = 404 (존재 여부 비노출)
    if todo is None or todo.user_id != user.id:
        raise not_found("Todo를 찾을 수 없습니다.")
    return todo


@router.post("", response_model=TodoResponse, status_code=201)
def create_todo(body: TodoCreateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    todo = Todo(user_id=user.id, content=body.content)
    db.add(todo)
    db.commit()
    return todo


@router.get("", response_model=list[TodoResponse])
def list_todos(
    status: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if status is not None and status not in TodoStatus.ALL:
        raise bad_request(message=f"status 필터는 {sorted(TodoStatus.ALL)} 중 하나여야 합니다.")
    stmt = select(Todo).where(Todo.user_id == user.id).order_by(Todo.created_at.desc(), Todo.id.desc())
    if status is not None:
        stmt = stmt.where(Todo.status == status)
    return list(db.scalars(stmt))


@router.patch("/{todo_id}", response_model=TodoResponse)
def update_todo(
    todo_id: int, body: TodoUpdateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    todo = _get_my_todo(db, user, todo_id)
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        if value is not None:
            setattr(todo, field, value)
    db.commit()
    return todo


@router.delete("/{todo_id}", status_code=204)
def delete_todo(todo_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    todo = _get_my_todo(db, user, todo_id)
    todo.soft_delete()
    db.commit()
