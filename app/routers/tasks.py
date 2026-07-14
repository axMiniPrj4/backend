from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import ProjectContext, get_project_context
from app.core.errors import ErrorCode, bad_request, forbidden, not_found
from app.core.pagination import DEFAULT_SIZE, parse_page_params, paginate
from app.db.session import get_db
from app.models import ProjectMember, Task, User
from app.models.task import TaskStatus
from app.schemas.common import PageResponse
from app.schemas.task import (
    GanttResponse,
    GanttTaskItem,
    TaskAssigneeResponse,
    TaskCreateRequest,
    TaskResponse,
    TaskStatusUpdateRequest,
    TaskUpdateRequest,
)

router = APIRouter(prefix="/api/projects/{project_id}", tags=["Task"])

_SORT_FIELDS = {"created_at", "title", "status", "start_date", "end_date"}


def _validate_dates(start, end):
    if start > end:
        raise bad_request(ErrorCode.INVALID_DATE_RANGE, "시작일은 종료일보다 늦을 수 없습니다.")


def _resolve_assignees(db: Session, project_id: int, assignee_ids: list[int]) -> list[User]:
    """담당자 목록 검증 — 전원이 프로젝트 멤버여야 한다. 중복은 제거."""
    ids = list(dict.fromkeys(assignee_ids))
    member_ids = set(
        db.scalars(
            select(ProjectMember.user_id).where(
                ProjectMember.project_id == project_id, ProjectMember.user_id.in_(ids)
            )
        )
    )
    invalid = [i for i in ids if i not in member_ids]
    if invalid:
        raise bad_request(message=f"담당자는 프로젝트 멤버여야 합니다: {invalid}")
    return list(db.scalars(select(User).where(User.id.in_(ids))))


def _get_task(db: Session, ctx: ProjectContext, task_id: int) -> Task:
    task = db.scalar(
        select(Task)
        .where(Task.id == task_id, Task.project_id == ctx.project.id)
        .options(selectinload(Task.assignees))
    )
    if task is None:
        raise not_found("업무를 찾을 수 없습니다.")
    return task


@router.post("/tasks", response_model=TaskResponse, status_code=201)
def create_task(body: TaskCreateRequest, ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    _validate_dates(body.start_date, body.end_date)
    # 미지정 시 생성자 자동 할당
    assignee_ids = body.assignee_ids or [ctx.user.id]
    assignees = _resolve_assignees(db, ctx.project.id, assignee_ids)
    task = Task(
        project_id=ctx.project.id,
        title=body.title,
        content=body.content,
        creator_id=ctx.user.id,
        start_date=body.start_date,
        end_date=body.end_date,
        assignees=assignees,
    )
    db.add(task)
    db.commit()
    return task


@router.get("/tasks", response_model=PageResponse[TaskResponse])
def list_tasks(
    status: str | None = Query(None),
    assignee_id: int | None = Query(None),
    page: int = Query(1),
    size: int = Query(DEFAULT_SIZE),
    sort: str | None = Query(None),
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    if status is not None and status not in TaskStatus.ALL:
        raise bad_request(message=f"status 필터는 {sorted(TaskStatus.ALL)} 중 하나여야 합니다.")
    params = parse_page_params(page, size, sort, _SORT_FIELDS)
    stmt = select(Task).where(Task.project_id == ctx.project.id).options(selectinload(Task.assignees))
    if status is not None:
        stmt = stmt.where(Task.status == status)
    if assignee_id is not None:
        stmt = stmt.where(Task.assignees.any(User.id == assignee_id))
    return paginate(db, stmt, Task, params)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    return _get_task(db, ctx, task_id)


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    body: TaskUpdateRequest,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    task = _get_task(db, ctx, task_id)
    # ④ 리소스 소유권: 작성자 또는 LEADER
    if not (ctx.is_leader or task.creator_id == ctx.user.id):
        raise forbidden("작성자 또는 팀장만 수정할 수 있습니다.")
    data = body.model_dump(exclude_unset=True)
    if "assignee_ids" in data:
        ids = data.pop("assignee_ids")
        if not ids:
            raise bad_request(message="담당자는 최소 1명이어야 합니다.")
        task.assignees = _resolve_assignees(db, ctx.project.id, ids)
    for field, value in data.items():
        setattr(task, field, value)
    _validate_dates(task.start_date, task.end_date)
    db.commit()
    return task


@router.patch("/tasks/{task_id}/status", response_model=TaskResponse)
def update_task_status(
    task_id: int,
    body: TaskStatusUpdateRequest,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    task = _get_task(db, ctx, task_id)
    # ④ 상태 변경 권한: 담당자 중 한 명 또는 LEADER (수정과 주체가 달라 엔드포인트 분리)
    if not (ctx.is_leader or ctx.user.id in task.assignee_ids):
        raise forbidden("담당자 또는 팀장만 상태를 변경할 수 있습니다.")
    task.status = body.status
    db.commit()
    return task


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    task = _get_task(db, ctx, task_id)
    if not (ctx.is_leader or task.creator_id == ctx.user.id):
        raise forbidden("작성자 또는 팀장만 삭제할 수 있습니다.")
    task.soft_delete()
    db.commit()


@router.get("/gantt", response_model=GanttResponse)
def get_gantt(ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    tasks = db.scalars(
        select(Task)
        .where(Task.project_id == ctx.project.id)
        .options(selectinload(Task.assignees))
        .order_by(Task.start_date.asc(), Task.id.asc())
    ).all()
    total = len(tasks)
    done = sum(1 for t in tasks if t.status == TaskStatus.DONE)
    progress = round(done / total * 100, 1) if total else 0.0
    return GanttResponse(
        project_id=ctx.project.id,
        total_tasks=total,
        done_tasks=done,
        progress=progress,
        tasks=[
            GanttTaskItem(
                id=t.id,
                title=t.title,
                assignees=[TaskAssigneeResponse.model_validate(u) for u in t.assignees],
                start_date=t.start_date,
                end_date=t.end_date,
                status=t.status,
            )
            for t in tasks
        ],
    )
