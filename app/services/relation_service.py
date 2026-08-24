from collections import defaultdict

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import ProjectContext
from app.core.errors import forbidden, not_found
from app.models import Doc, OprReport, OprRow, Task
from app.models.relation import OprReportDocLink, TaskDocLink


def _get_task(db: Session, ctx: ProjectContext, task_id: int) -> Task:
    task = db.scalar(
        select(Task)
        .where(Task.id == task_id, Task.project_id == ctx.project.id)
        .options(selectinload(Task.assignees))
    )
    if task is None:
        raise not_found("업무를 찾을 수 없습니다.")
    return task


def _get_doc(db: Session, ctx: ProjectContext, doc_id: int) -> Doc:
    doc = db.scalar(
        select(Doc)
        .where(Doc.id == doc_id, Doc.project_id == ctx.project.id)
        .options(selectinload(Doc.versions))
    )
    if doc is None:
        raise not_found("프로젝트 자료를 찾을 수 없습니다.")
    return doc


def _get_report(db: Session, ctx: ProjectContext, report_id: int) -> OprReport:
    report = db.scalar(
        select(OprReport)
        .where(OprReport.id == report_id, OprReport.project_id == ctx.project.id)
        .options(selectinload(OprReport.rows), selectinload(OprReport.author))
    )
    if report is None:
        raise not_found("OPR을 찾을 수 없습니다.")
    return report


def _can_manage_task(ctx: ProjectContext, task: Task) -> bool:
    return ctx.is_leader or task.creator_id == ctx.user.id or ctx.user.id in task.assignee_ids


def _doc_item(doc: Doc, relation_types: set[str] | None = None) -> dict:
    latest = doc.latest_version
    return {
        "id": doc.id,
        "title": doc.title,
        "latest_file_name": latest.file_name if latest else None,
        "version_no": latest.version_no if latest else None,
        "relation_types": sorted(relation_types or set()),
    }


def _task_item(task: Task) -> dict:
    return {"id": task.id, "title": task.title, "status": task.status}


def _opr_item(report: OprReport, matching_rows: list[OprRow] | None = None) -> dict:
    return {
        "report_id": report.id,
        "report_date": report.report_date,
        "author_id": report.author_id,
        "author_nickname": report.author_nickname,
        "author_name": report.author_name,
        "status": report.status,
        "matching_rows": [
            {"row_id": row.id, "section_type": row.section_type, "content": row.content}
            for row in (matching_rows or [])
        ],
    }


def link_task_doc(db: Session, ctx: ProjectContext, task_id: int, doc_id: int) -> TaskDocLink:
    task = _get_task(db, ctx, task_id)
    _get_doc(db, ctx, doc_id)
    if not _can_manage_task(ctx, task):
        raise forbidden("Task 담당자·작성자 또는 팀장만 자료를 연결할 수 있습니다.")
    link = db.get(TaskDocLink, (task_id, doc_id))
    if link is None:
        link = TaskDocLink(task_id=task_id, doc_id=doc_id, project_id=ctx.project.id, linked_by=ctx.user.id)
        db.add(link)
        db.commit()
        db.refresh(link)
    return link


def unlink_task_doc(db: Session, ctx: ProjectContext, task_id: int, doc_id: int) -> None:
    task = _get_task(db, ctx, task_id)
    link = db.get(TaskDocLink, (task_id, doc_id))
    if link is None or link.project_id != ctx.project.id:
        raise not_found("Task와 자료의 연결을 찾을 수 없습니다.")
    if not (ctx.is_leader or link.linked_by == ctx.user.id or task.creator_id == ctx.user.id):
        raise forbidden("연결한 사용자·Task 작성자 또는 팀장만 연결을 해제할 수 있습니다.")
    db.delete(link)
    db.commit()


def link_opr_doc(db: Session, ctx: ProjectContext, report_id: int, doc_id: int) -> OprReportDocLink:
    report = _get_report(db, ctx, report_id)
    _get_doc(db, ctx, doc_id)
    if not (ctx.is_leader or report.author_id == ctx.user.id):
        raise forbidden("OPR 작성자 또는 팀장만 자료를 연결할 수 있습니다.")
    link = db.get(OprReportDocLink, (report_id, doc_id))
    if link is None:
        link = OprReportDocLink(report_id=report_id, doc_id=doc_id, project_id=ctx.project.id, linked_by=ctx.user.id)
        db.add(link)
        db.commit()
        db.refresh(link)
    return link


def unlink_opr_doc(db: Session, ctx: ProjectContext, report_id: int, doc_id: int) -> None:
    report = _get_report(db, ctx, report_id)
    link = db.get(OprReportDocLink, (report_id, doc_id))
    if link is None or link.project_id != ctx.project.id:
        raise not_found("OPR과 자료의 연결을 찾을 수 없습니다.")
    if not (ctx.is_leader or report.author_id == ctx.user.id or link.linked_by == ctx.user.id):
        raise forbidden("OPR 작성자·연결한 사용자 또는 팀장만 연결을 해제할 수 있습니다.")
    db.delete(link)
    db.commit()


def get_task_relations(db: Session, ctx: ProjectContext, task_id: int) -> dict:
    task = _get_task(db, ctx, task_id)
    rows = list(
        db.scalars(
            select(OprRow)
            .join(OprReport, OprReport.id == OprRow.report_id)
            .where(OprRow.task_id == task.id, OprReport.project_id == ctx.project.id)
            .options(selectinload(OprRow.report).selectinload(OprReport.author))
            .order_by(OprReport.report_date.desc(), OprReport.id.desc(), OprRow.sort_order.asc())
        ).all()
    )
    grouped: dict[int, list[OprRow]] = defaultdict(list)
    reports: dict[int, OprReport] = {}
    for row in rows:
        grouped[row.report_id].append(row)
        reports[row.report_id] = row.report

    relation_types: dict[int, set[str]] = defaultdict(set)
    direct_doc_ids = set(
        db.scalars(select(TaskDocLink.doc_id).where(TaskDocLink.task_id == task.id, TaskDocLink.project_id == ctx.project.id))
    )
    for doc_id in direct_doc_ids:
        relation_types[doc_id].add("TASK")
    for row in rows:
        if row.doc_id is not None:
            relation_types[row.doc_id].add("OPR_ROW")
    docs = []
    if relation_types:
        docs = list(
            db.scalars(
                select(Doc).where(Doc.id.in_(relation_types)).options(selectinload(Doc.versions)).order_by(Doc.id.asc())
            ).all()
        )
    return {
        "task": _task_item(task),
        "opr_reports": [_opr_item(reports[report_id], grouped[report_id]) for report_id in reports],
        "documents": [_doc_item(doc, relation_types[doc.id]) for doc in docs],
    }


def get_opr_relations(db: Session, ctx: ProjectContext, report_id: int) -> dict:
    report = _get_report(db, ctx, report_id)
    task_ids = {row.task_id for row in report.rows if row.task_id is not None}
    tasks = []
    if task_ids:
        tasks = list(db.scalars(select(Task).where(Task.id.in_(task_ids)).order_by(Task.id.asc())).all())

    relation_types: dict[int, set[str]] = defaultdict(set)
    direct_doc_ids = set(
        db.scalars(
            select(OprReportDocLink.doc_id).where(
                OprReportDocLink.report_id == report.id,
                OprReportDocLink.project_id == ctx.project.id,
            )
        )
    )
    for doc_id in direct_doc_ids:
        relation_types[doc_id].add("OPR_DIRECT")
    for row in report.rows:
        if row.doc_id is not None:
            relation_types[row.doc_id].add("OPR_ROW")
    if task_ids:
        for doc_id in db.scalars(
            select(TaskDocLink.doc_id).where(
                TaskDocLink.project_id == ctx.project.id,
                TaskDocLink.task_id.in_(task_ids),
            )
        ):
            relation_types[doc_id].add("TASK")

    docs = []
    if relation_types:
        docs = list(
            db.scalars(
                select(Doc).where(Doc.id.in_(relation_types)).options(selectinload(Doc.versions)).order_by(Doc.id.asc())
            ).all()
        )
    return {
        "report_id": report.id,
        "tasks": [_task_item(task) for task in tasks],
        "documents": [_doc_item(doc, relation_types[doc.id]) for doc in docs],
    }


def get_doc_relations(db: Session, ctx: ProjectContext, doc_id: int) -> dict:
    _get_doc(db, ctx, doc_id)
    task_ids = set(
        db.scalars(
            select(TaskDocLink.task_id).where(
                TaskDocLink.project_id == ctx.project.id,
                TaskDocLink.doc_id == doc_id,
            )
        )
    )
    tasks = []
    if task_ids:
        tasks = list(db.scalars(select(Task).where(Task.id.in_(task_ids)).order_by(Task.id.asc())).all())

    direct_report_ids = set(
        db.scalars(
            select(OprReportDocLink.report_id).where(
                OprReportDocLink.project_id == ctx.project.id,
                OprReportDocLink.doc_id == doc_id,
            )
        )
    )
    row_stmt = select(OprRow.report_id).join(OprReport, OprReport.id == OprRow.report_id).where(
        OprReport.project_id == ctx.project.id,
        or_(OprRow.doc_id == doc_id, OprRow.task_id.in_(task_ids)) if task_ids else OprRow.doc_id == doc_id,
    )
    report_ids = direct_report_ids | set(db.scalars(row_stmt))
    reports = []
    if report_ids:
        reports = list(
            db.scalars(
                select(OprReport)
                .where(OprReport.id.in_(report_ids))
                .options(selectinload(OprReport.author))
                .order_by(OprReport.report_date.desc(), OprReport.id.desc())
            ).all()
        )
    return {
        "doc_id": doc_id,
        "tasks": [_task_item(task) for task in tasks],
        "opr_reports": [_opr_item(report) for report in reports],
    }
