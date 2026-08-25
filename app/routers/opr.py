from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import ProjectContext, get_project_context
from app.core.errors import bad_request, forbidden, not_found
from app.db.session import get_db
from app.models import Doc, OprReport, OprRow, Task
from app.schemas.opr import OprReportResponse, OprReportSaveRequest, OprSourceResponse

router = APIRouter(prefix="/api/projects/{project_id}/opr", tags=["OPR"])


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


@router.get("/source/{report_date}", response_model=OprSourceResponse)
def get_opr_source(
    report_date: date,
    ctx: ProjectContext = Depends(get_project_context),
    _db: Session = Depends(get_db),
):
    """빈 OPR 초안용. Task/자료실을 할일 칸에 자동으로 채우지 않는다."""
    return OprSourceResponse(project_id=ctx.project.id, report_date=report_date, rows=[])


@router.get("/reports", response_model=list[OprReportResponse])
def list_opr_reports(
    start_date: date = Query(..., description="조회 시작일(포함)"),
    end_date: date = Query(..., description="조회 종료일(포함)"),
    scope: str = Query("me", description="me | team"),
    task_id: int | None = Query(None),
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    """일/주/월/프로젝트 기간 OPR 목록. 포트폴리오·엑셀 내보내기용."""
    if end_date < start_date:
        raise bad_request(message="종료일은 시작일보다 빠를 수 없습니다.")
    if (end_date - start_date).days > 400:
        raise bad_request(message="조회 기간은 최대 400일까지 가능합니다.")
    if scope not in {"me", "team"}:
        raise bad_request(message="scope는 me 또는 team 이어야 합니다.")

    stmt = (
        select(OprReport)
        .where(
            OprReport.project_id == ctx.project.id,
            OprReport.report_date >= start_date,
            OprReport.report_date <= end_date,
        )
        .options(selectinload(OprReport.rows), selectinload(OprReport.author))
        .order_by(OprReport.report_date.asc(), OprReport.author_id.asc(), OprReport.id.asc())
    )
    if scope == "me":
        stmt = stmt.where(OprReport.author_id == ctx.user.id)
    if task_id is not None:
        stmt = stmt.where(OprReport.rows.any(OprRow.task_id == task_id))
    return list(db.scalars(stmt).all())


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
        # 삭제된 Task도 같은 프로젝트면 기존 OPR 행 재저장(자료 해제 등)을 허용
        valid_task_ids = set(
            db.scalars(
                select(Task.id)
                .where(Task.project_id == project_id, Task.id.in_(task_ids))
                .execution_options(include_deleted=True)
            )
        )
        if valid_task_ids != task_ids:
            raise bad_request(message="다른 프로젝트의 Task는 OPR에 연결할 수 없습니다.")
    if doc_ids:
        # 프로젝트 자료 + 공통 자료(project_id NULL) 허용
        valid_doc_ids = set(
            db.scalars(
                select(Doc.id)
                .where(
                    Doc.id.in_(doc_ids),
                    or_(Doc.project_id == project_id, Doc.project_id.is_(None)),
                )
                .execution_options(include_deleted=True)
            )
        )
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
