from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.deps import ProjectContext, get_project_context
from app.core.errors import ErrorCode, bad_request, forbidden, not_found
from app.core.pagination import DEFAULT_SIZE, parse_page_params, paginate
from app.db.session import get_db
from app.models import OprReport, OprRow, ProjectMember, Task, TaskHistory, User
from app.models.task import TaskPriority, TaskStatus
from app.schemas.common import PageResponse
from app.schemas.task import (
    GanttResponse,
    GanttTaskItem,
    TaskAssigneeResponse,
    TaskCreateRequest,
    TaskHistoryResponse,
    TaskLinkSummaryItem,
    TaskLinkSummaryResponse,
    TaskReorderRequest,
    TaskResponse,
    TaskStatusUpdateRequest,
    TaskUpdateRequest,
)
from app.services.notifications import notify_task_assigned, notify_task_status
from app.services.task_history import add_task_history

router = APIRouter(prefix="/api/projects/{project_id}", tags=["Task"])

_SORT_FIELDS = {"id", "sort_order", "created_at", "title", "status", "start_date", "end_date", "priority"}

_STATUS_LABEL = {
    TaskStatus.TODO: "할 일",
    TaskStatus.IN_PROGRESS: "진행 중",
    TaskStatus.DONE: "완료",
}

_PRIORITY_LABEL = {
    TaskPriority.HIGH: "상",
    TaskPriority.MEDIUM: "중",
    TaskPriority.LOW: "하",
}


def _validate_dates(start, end, project=None):
    if start > end:
        raise bad_request(ErrorCode.INVALID_DATE_RANGE, "시작일은 종료일보다 늦을 수 없습니다.")
    if project is None:
        return
    p_start = project.start_date
    p_end = project.end_date
    if p_start and start < p_start:
        raise bad_request(
            ErrorCode.INVALID_DATE_RANGE,
            f"작업 시작일은 프로젝트 시작일({p_start.isoformat()}) 이전일 수 없습니다.",
        )
    if p_end and end > p_end:
        raise bad_request(
            ErrorCode.INVALID_DATE_RANGE,
            f"작업 종료일은 프로젝트 마감일({p_end.isoformat()}) 이후일 수 없습니다.",
        )
    if p_start and end < p_start:
        raise bad_request(
            ErrorCode.INVALID_DATE_RANGE,
            "작업 기간이 프로젝트 기간을 벗어났습니다.",
        )
    if p_end and start > p_end:
        raise bad_request(
            ErrorCode.INVALID_DATE_RANGE,
            "작업 기간이 프로젝트 기간을 벗어났습니다.",
        )


def _next_sort_order(db: Session, project_id: int) -> int:
    """프로젝트 내 마지막 순서 + 1 (목록 맨 아래)."""
    current = db.scalar(
        select(func.max(Task.sort_order)).where(
            Task.project_id == project_id, Task.deleted_at.is_(None)
        )
    )
    return int(current or 0) + 1


def _placement_sort_order(db: Session, project_id: int, category: str, work_group: str) -> int:
    """새 작업이 들어갈 자리 — 같은 구분(되도록 같은 작업 그룹)의 마지막 바로 뒤.

    무조건 맨 아래에 붙이면 나중에 만든 작업이 구분과 무관하게 꼬리에 쌓여,
    WBS 가 「기획 … 배포 → 기타 → 배포 → 기획」처럼 조각난다. 화면이 저장된
    순서를 그대로 그리기 때문에 이 조각남이 그대로 보인다.

    같은 구분이 여러 군데 흩어져 있으면 마지막에 나온 자리를 기준으로 삼는다.
    """
    rows = db.execute(
        select(Task.sort_order, Task.category, Task.work_group)
        .where(Task.project_id == project_id, Task.deleted_at.is_(None))
        .order_by(Task.sort_order, Task.id)
    ).all()
    if not rows:
        return 1

    last_in_group = None
    last_in_category = None
    for order, row_category, row_work_group in rows:
        if row_category != category:
            continue
        last_in_category = order
        if row_work_group == work_group:
            last_in_group = order

    anchor = last_in_group if last_in_group is not None else last_in_category
    if anchor is None:
        return int(rows[-1][0]) + 1
    return int(anchor) + 1


def _shift_sort_orders(db: Session, project_id: int, from_order: int) -> None:
    """끼워 넣을 자리부터 뒤를 한 칸씩 민다.

    (project_id, sort_order) 인덱스가 비유일이라 중간 단계 충돌을 걱정하지 않아도 된다.
    소프트 삭제된 행도 함께 민다 — 되살릴 때 순서가 어긋나지 않도록.
    """
    db.execute(
        update(Task)
        .where(Task.project_id == project_id, Task.sort_order >= from_order)
        .values(sort_order=Task.sort_order + 1)
        .execution_options(synchronize_session=False)
    )


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


def _pick_primary(assignees: list[User], requested: int | None) -> int | None:
    """주담당자 결정 — 요청값이 담당자 목록에 있으면 그것, 없으면 첫 담당자."""
    ids = [u.id for u in assignees]
    if not ids:
        return None
    if requested is not None:
        if requested not in ids:
            raise bad_request(message="주담당자는 담당자 중에서 선택해야 합니다.")
        return requested
    return ids[0]


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
    _validate_dates(body.start_date, body.end_date, ctx.project)
    # 미지정 시 생성자 자동 할당
    assignee_ids = body.assignee_ids or [ctx.user.id]
    assignees = _resolve_assignees(db, ctx.project.id, assignee_ids)

    category = (body.category or "기타").strip() or "기타"
    work_group = (body.work_group or "").strip()
    if body.append:
        sort_order = _next_sort_order(db, ctx.project.id)
    else:
        sort_order = _placement_sort_order(db, ctx.project.id, category, work_group)
        _shift_sort_orders(db, ctx.project.id, sort_order)

    task = Task(
        project_id=ctx.project.id,
        title=body.title,
        content=body.content,
        creator_id=ctx.user.id,
        start_date=body.start_date,
        end_date=body.end_date,
        assignees=assignees,
        category=category,
        work_group=work_group,
        color=body.color,
        priority=body.priority or TaskPriority.MEDIUM,
        sort_order=sort_order,
        primary_assignee_id=_pick_primary(assignees, body.primary_assignee_id),
    )
    db.add(task)
    db.flush()
    add_task_history(
        db,
        task=task,
        actor_id=ctx.user.id,
        event_type="CREATED",
        message=f"{ctx.user.nickname}님이 작업을 생성했습니다.",
    )
    notify_task_assigned(
        db,
        task=task,
        actor_id=ctx.user.id,
        actor_nickname=ctx.user.nickname,
        new_assignee_ids=[u.id for u in assignees],
    )
    db.commit()
    db.refresh(task)
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


@router.patch("/tasks/reorder", response_model=list[TaskResponse])
def reorder_tasks(
    body: TaskReorderRequest,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    """WBS 행 순서 일괄 저장. 개별 PATCH를 반복하면 중간 실패 시 순서가 깨지므로 한 번에 처리."""
    if not ctx.is_editor:
        raise forbidden("보기 권한만 있어 순서를 변경할 수 없습니다.")

    ids = [item.id for item in body.items]
    if len(set(ids)) != len(ids):
        raise bad_request(message="같은 작업이 중복으로 전달되었습니다.")

    rows = db.scalars(
        select(Task)
        .where(Task.project_id == ctx.project.id, Task.id.in_(ids))
        .options(selectinload(Task.assignees))
    ).all()
    by_id = {task.id: task for task in rows}
    missing = [task_id for task_id in ids if task_id not in by_id]
    if missing:
        raise not_found(f"작업을 찾을 수 없습니다: {missing}")

    for item in body.items:
        task = by_id[item.id]
        task.sort_order = item.sort_order
        if item.work_group is not None:
            task.work_group = item.work_group.strip()
        # 다른 구분으로 옮긴 경우에만 전달된다. 빈 값으로 지우는 것은 막는다.
        if item.category is not None:
            category = item.category.strip()
            if not category:
                raise bad_request(message="구분은 빈 값일 수 없습니다.")
            task.category = category

    db.commit()
    return sorted(rows, key=lambda t: (t.sort_order, t.id))


# 리터럴 경로라 "/tasks/{task_id}" 보다 먼저 선언해야 한다.
@router.get("/tasks/link-summary", response_model=TaskLinkSummaryResponse)
def task_link_summary(
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    """작업마다 OPR 몇 줄·몇 건에 연결돼 있는지.

    WBS 엑셀 업로드는 기존 작업을 전부 지우고 새로 만든다. 지워진 작업을 가리키던
    OPR 행은 이름을 잃고 「Task #123」으로만 남으므로, 삭제 전에 경고할 수 있도록
    연결 건수를 한 번에 내려준다.
    """
    rows = db.execute(
        select(
            OprRow.task_id,
            func.count(OprRow.id),
            func.count(func.distinct(OprRow.report_id)),
        )
        .join(OprReport, OprReport.id == OprRow.report_id)
        .join(Task, Task.id == OprRow.task_id)
        .where(
            OprReport.project_id == ctx.project.id,
            Task.project_id == ctx.project.id,
            # 이미 지워진 작업을 가리키는 행은 셀 필요가 없다 — 이미 끊긴 연결이다
            Task.deleted_at.is_(None),
        )
        .group_by(OprRow.task_id)
    ).all()
    return TaskLinkSummaryResponse(
        items=[
            TaskLinkSummaryItem(
                task_id=task_id, opr_row_count=row_count, opr_report_count=report_count
            )
            for task_id, row_count, report_count in rows
        ]
    )


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
    # ④ 편집 권한: 프로젝트 편집자(EDITOR) 또는 LEADER — VIEWER만 차단
    if not ctx.is_editor:
        raise forbidden("보기 권한만 있어 편집할 수 없습니다.")
    data = body.model_dump(exclude_unset=True)
    prev_assignee_ids = set(task.assignee_ids)
    prev_priority = task.priority
    requested_primary = data.pop("primary_assignee_id", None)
    primary_explicit = "primary_assignee_id" in body.model_fields_set
    if "assignee_ids" in data:
        ids = data.pop("assignee_ids")
        if not ids:
            raise bad_request(message="담당자는 최소 1명이어야 합니다.")
        task.assignees = _resolve_assignees(db, ctx.project.id, ids)
    # 담당자가 바뀌면 기존 주담당자가 목록에서 빠질 수 있으므로 항상 재검증한다.
    if primary_explicit or task.primary_assignee_id not in task.assignee_ids:
        task.primary_assignee_id = _pick_primary(
            task.assignees,
            requested_primary if primary_explicit else None,
        )
    if "category" in data and data["category"] is not None:
        data["category"] = str(data["category"]).strip() or "기타"
    if "work_group" in data and data["work_group"] is not None:
        data["work_group"] = str(data["work_group"]).strip()
    for field, value in data.items():
        setattr(task, field, value)
    _validate_dates(task.start_date, task.end_date, ctx.project)
    added = [uid for uid in task.assignee_ids if uid not in prev_assignee_ids]
    if added:
        notify_task_assigned(
            db,
            task=task,
            actor_id=ctx.user.id,
            actor_nickname=ctx.user.nickname,
            new_assignee_ids=added,
        )
        names = ", ".join(u.nickname for u in task.assignees if u.id in added)
        add_task_history(
            db,
            task=task,
            actor_id=ctx.user.id,
            event_type="ASSIGNED",
            message=f"{ctx.user.nickname}님이 담당자를 추가했습니다: {names}",
        )
    removed = prev_assignee_ids - set(task.assignee_ids)
    if removed:
        add_task_history(
            db,
            task=task,
            actor_id=ctx.user.id,
            event_type="UNASSIGNED",
            message=f"{ctx.user.nickname}님이 담당자를 변경했습니다.",
        )
    if "priority" in body.model_dump(exclude_unset=True) and task.priority != prev_priority:
        add_task_history(
            db,
            task=task,
            actor_id=ctx.user.id,
            event_type="PRIORITY",
            message=(
                f"{ctx.user.nickname}님이 우선순위를 "
                f"{_PRIORITY_LABEL.get(prev_priority, prev_priority)} → "
                f"{_PRIORITY_LABEL.get(task.priority, task.priority)}(으)로 변경했습니다."
            ),
        )
    db.commit()
    db.refresh(task)
    return task


@router.patch("/tasks/{task_id}/status", response_model=TaskResponse)
def update_task_status(
    task_id: int,
    body: TaskStatusUpdateRequest,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    task = _get_task(db, ctx, task_id)
    # ④ 상태 변경 권한: 프로젝트 편집자(EDITOR) 또는 LEADER — VIEWER만 차단
    if not ctx.is_editor:
        raise forbidden("보기 권한만 있어 상태를 변경할 수 없습니다.")
    if body.status == TaskStatus.DONE and not task.assignee_ids:
        raise bad_request(
            ErrorCode.VALIDATION_ERROR,
            "담당자가 없는 작업은 완료로 변경할 수 없습니다.",
        )
    prev_status = task.status
    task.status = body.status
    if body.status != prev_status:
        notify_task_status(
            db,
            task=task,
            actor_id=ctx.user.id,
            actor_nickname=ctx.user.nickname,
            new_status=body.status,
        )
        add_task_history(
            db,
            task=task,
            actor_id=ctx.user.id,
            event_type="STATUS",
            message=(
                f"{ctx.user.nickname}님이 상태를 "
                f"{_STATUS_LABEL.get(prev_status, prev_status)} → "
                f"{_STATUS_LABEL.get(body.status, body.status)}(으)로 변경했습니다."
            ),
        )
    db.commit()
    db.refresh(task)
    return task


@router.get("/tasks/{task_id}/history", response_model=list[TaskHistoryResponse])
def list_task_history(
    task_id: int,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    task = _get_task(db, ctx, task_id)
    rows = db.scalars(
        select(TaskHistory)
        .where(TaskHistory.task_id == task.id)
        .options(selectinload(TaskHistory.actor))
        .order_by(TaskHistory.created_at.desc(), TaskHistory.id.desc())
        .limit(50)
    ).all()
    return list(rows)


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    task = _get_task(db, ctx, task_id)
    if not ctx.is_editor:
        raise forbidden("보기 권한만 있어 삭제할 수 없습니다.")
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
                priority=t.priority or TaskPriority.MEDIUM,
                category=t.category or "기타",
                work_group=t.work_group or "",
                color=t.color,
            )
            for t in tasks
        ],
    )
