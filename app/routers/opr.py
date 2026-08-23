from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import ProjectContext, get_project_context
from app.core.errors import bad_request, forbidden, not_found
from app.db.session import get_db
from app.models import Doc, OprReport, OprRow, Task, TaskHistory, User
from app.models.opr import OprSection
from app.models.task import TaskStatus
from app.schemas.opr import OprReportResponse, OprReportSaveRequest, OprRowInput, OprSourceResponse

router = APIRouter(prefix="/api/projects/{project_id}/opr", tags=["OPR"])
KST = ZoneInfo("Asia/Seoul")


def _day_bounds_utc(report_date: date):
    start_kst = datetime.combine(report_date, time.min, tzinfo=KST)
    end_kst = start_kst + timedelta(days=1)
    return (
        start_kst.astimezone(timezone.utc).replace(tzinfo=None),
        end_kst.astimezone(timezone.utc).replace(tzinfo=None),
    )


def _get_report(db: Session, project_id: int, report_date: date, author_id: int):
    return db.scalar(
        select(OprReport)
        .where(
            OprReport.project_id == project_id,
            OprReport.report_date == report_date,
            OprReport.author_id == author_id,
        )
        .options(selectinload(OprReport.rows), selectinload(OprReport.author))
    )


def _assignee_names(task: Task) -> str:
    return ", ".join(user.nickname for user in task.assignees)


def _task_row(task: Task, section_type: str, sort_order: int, *, report_date=None) -> OprRowInput:
    status = "진행 중" if task.status == TaskStatus.IN_PROGRESS else "예정"
    completed_date = None
    planned_date = task.start_date
    if section_type == OprSection.COMPLETED:
        status = "완료"
        completed_date = report_date
    elif section_type == OprSection.ISSUE:
        status = "지연"
    return OprRowInput(
        section_type=section_type,
        content=task.title,
        status=status,
        assignee_name=_assignee_names(task),
        planned_date=planned_date,
        completed_date=completed_date,
        task_id=task.id,
        source="AUTO",
        sort_order=sort_order,
        issue_request="완료 예정일과 대응 방안을 확인해 주세요." if section_type == OprSection.ISSUE else None,
    )


def _carried_today_rows(
    db: Session, project_id: int, author_id: int, report_date: date, start_index: int
) -> list[OprRowInput]:
    """가장 최근 저장분에서 완료되지 않은 수동 '오늘 할 일'을 오늘 날짜로 이월한다 (KnotQ Daily Queue 참고)."""
    previous = db.scalar(
        select(OprReport)
        .where(
            OprReport.project_id == project_id,
            OprReport.author_id == author_id,
            OprReport.report_date < report_date,
        )
        .options(selectinload(OprReport.rows))
        .order_by(OprReport.report_date.desc())
        .limit(1)
    )
    if previous is None:
        return []
    pending = [
        row for row in previous.rows
        if row.section_type == OprSection.TODAY and row.task_id is None and (row.status or "") != "완료"
    ]
    return [
        OprRowInput(
            section_type=OprSection.TODAY,
            content=row.content,
            status=row.status,
            assignee_name=row.assignee_name,
            planned_date=report_date,
            artifact_link=row.artifact_link,
            issue_request=row.issue_request,
            source="CARRIED",
            sort_order=start_index + index,
        )
        for index, row in enumerate(pending)
    ]


@router.get("/source/{report_date}", response_model=OprSourceResponse)
def get_opr_source(
    report_date: date,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    """선택 날짜의 Task·완료 이력·자료실을 OPR 편집 행으로 변환한다."""
    tasks = list(
        db.scalars(
            select(Task)
            .where(
                Task.project_id == ctx.project.id,
                Task.assignees.any(User.id == ctx.user.id),
            )
            .options(selectinload(Task.assignees))
            .order_by(Task.start_date.asc(), Task.id.asc())
        ).all()
    )
    task_by_id = {task.id: task for task in tasks}
    tomorrow = report_date + timedelta(days=1)
    rows: list[OprRowInput] = []

    today_tasks = [
        task for task in tasks
        if task.status != TaskStatus.DONE and task.start_date <= report_date <= task.end_date
    ]
    rows.extend(_task_row(task, OprSection.TODAY, index, report_date=report_date) for index, task in enumerate(today_tasks))
    rows.extend(_carried_today_rows(db, ctx.project.id, ctx.user.id, report_date, len(today_tasks)))

    start_utc, end_utc = _day_bounds_utc(report_date)
    completed_histories = db.scalars(
        select(TaskHistory)
        .where(
            TaskHistory.project_id == ctx.project.id,
            TaskHistory.event_type == "STATUS",
            TaskHistory.created_at >= start_utc,
            TaskHistory.created_at < end_utc,
            TaskHistory.message.contains("→ 완료"),
        )
        .order_by(TaskHistory.created_at.asc(), TaskHistory.id.asc())
    ).all()
    completed_ids = list(dict.fromkeys(row.task_id for row in completed_histories))
    completed_tasks = [task_by_id[task_id] for task_id in completed_ids if task_id in task_by_id]
    rows.extend(
        _task_row(task, OprSection.COMPLETED, index, report_date=report_date)
        for index, task in enumerate(completed_tasks)
    )

    tomorrow_tasks = [
        task for task in tasks
        if task.status != TaskStatus.DONE and task.start_date <= tomorrow <= task.end_date
    ]
    rows.extend(
        _task_row(task, OprSection.TOMORROW, index, report_date=report_date)
        for index, task in enumerate(tomorrow_tasks)
    )

    docs = db.scalars(
        select(Doc)
        .where(
            Doc.project_id == ctx.project.id,
            Doc.user_id == ctx.user.id,
            Doc.updated_at >= start_utc,
            Doc.updated_at < end_utc,
        )
        .options(selectinload(Doc.versions))
        .order_by(Doc.updated_at.asc(), Doc.id.asc())
    ).all()
    for index, doc in enumerate(docs):
        latest = doc.latest_version
        rows.append(
            OprRowInput(
                section_type=OprSection.ARTIFACT,
                content=doc.title,
                status="완료",
                assignee_name=doc.author.nickname if doc.author else None,
                completed_date=report_date,
                artifact_link=f"/archive/{doc.id}",
                doc_id=doc.id,
                source="AUTO",
                sort_order=index,
                issue_request=latest.file_name if latest else None,
            )
        )

    overdue_tasks = [task for task in tasks if task.status != TaskStatus.DONE and task.end_date < report_date]
    rows.extend(
        _task_row(task, OprSection.ISSUE, index, report_date=report_date)
        for index, task in enumerate(overdue_tasks)
    )

    return OprSourceResponse(project_id=ctx.project.id, report_date=report_date, rows=rows)


@router.get("/{report_date}", response_model=OprReportResponse)
def get_opr(
    report_date: date,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    report = _get_report(db, ctx.project.id, report_date, ctx.user.id)
    if report is None:
        raise not_found("해당 날짜의 OPR이 없습니다.")
    return report


@router.get("/team/{report_date}", response_model=list[OprReportResponse])
def get_team_opr(
    report_date: date,
    task_id: int | None = Query(None),
    author_id: int | None = Query(None),
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    """선택 날짜에 프로젝트 멤버들이 작성한 개인 OPR을 작성자별로 반환한다."""
    stmt = (
        select(OprReport)
        .where(OprReport.project_id == ctx.project.id, OprReport.report_date == report_date)
        .options(selectinload(OprReport.rows), selectinload(OprReport.author))
        .order_by(OprReport.author_id.asc(), OprReport.id.asc())
    )
    if task_id is not None:
        stmt = stmt.where(OprReport.rows.any(OprRow.task_id == task_id))
    if author_id is not None:
        stmt = stmt.where(OprReport.author_id == author_id)
    reports = db.scalars(stmt).all()
    return list(reports)


def _validate_linked_resources(db: Session, project_id: int, body: OprReportSaveRequest) -> None:
    task_ids = {row.task_id for row in body.rows if row.task_id is not None}
    doc_ids = {row.doc_id for row in body.rows if row.doc_id is not None}
    if task_ids:
        valid_task_ids = set(db.scalars(select(Task.id).where(Task.project_id == project_id, Task.id.in_(task_ids))))
        if valid_task_ids != task_ids:
            raise bad_request(message="다른 프로젝트의 Task는 OPR에 연결할 수 없습니다.")
    if doc_ids:
        valid_doc_ids = set(db.scalars(select(Doc.id).where(Doc.project_id == project_id, Doc.id.in_(doc_ids))))
        if valid_doc_ids != doc_ids:
            raise bad_request(message="다른 프로젝트의 자료는 OPR에 연결할 수 없습니다.")


@router.put("/{report_date}", response_model=OprReportResponse)
def save_opr(
    report_date: date,
    body: OprReportSaveRequest,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    _validate_linked_resources(db, ctx.project.id, body)
    report = _get_report(db, ctx.project.id, report_date, ctx.user.id)
    if report is None:
        report = OprReport(
            project_id=ctx.project.id,
            report_date=report_date,
            status=body.status,
            author_id=ctx.user.id,
        )
        db.add(report)
    else:
        report.status = body.status
        report.rows.clear()

    report.rows.extend(
        OprRow(
            section_type=row.section_type,
            content=row.content.strip(),
            status=row.status,
            assignee_name=row.assignee_name,
            planned_date=row.planned_date,
            completed_date=row.completed_date,
            artifact_link=row.artifact_link,
            issue_request=row.issue_request,
            task_id=row.task_id,
            doc_id=row.doc_id,
            source=row.source,
            sort_order=index,
        )
        for index, row in enumerate(body.rows)
    )
    db.commit()
    return _get_report(db, ctx.project.id, report_date, ctx.user.id)


@router.delete("/{report_date}", status_code=204)
def delete_opr(
    report_date: date,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    report = _get_report(db, ctx.project.id, report_date, ctx.user.id)
    if report is None:
        raise not_found("해당 날짜의 OPR이 없습니다.")
    if not (ctx.is_leader or report.author_id == ctx.user.id):
        raise forbidden("작성자 또는 팀장만 OPR을 삭제할 수 있습니다.")
    db.delete(report)
    db.commit()
