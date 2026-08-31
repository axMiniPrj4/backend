from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import ProjectContext, get_project_context
from app.core.errors import bad_request, forbidden, not_found
from app.db.session import get_db
from app.models import Doc, OprReport, OprRow, OprRowDoc, Task
from app.models.opr_ai import OprAiRecord
from app.schemas.opr import OprReportResponse, OprReportSaveRequest, OprSourceResponse
from app.schemas.opr_ai import OprAiRecordInput, OprAiRecordResponse, OprAiRecordUpdate
from app.services import opr_ai_service

router = APIRouter(prefix="/api/projects/{project_id}/opr", tags=["OPR"])

# 응답에 AI 기록까지 담기므로 조회 3곳에서 같은 eager load 를 쓴다 (N+1 방지)
_REPORT_LOAD = (
    selectinload(OprReport.rows).selectinload(OprRow.doc_links),
    selectinload(OprReport.author),
    selectinload(OprReport.ai_records).selectinload(OprAiRecord.providers),
    selectinload(OprReport.ai_records).selectinload(OprAiRecord.task_links),
    selectinload(OprReport.ai_records).selectinload(OprAiRecord.doc_links),
)


def _get_report(db: Session, project_id: int, report_date: date, author_id: int):
    return db.scalar(
        select(OprReport)
        .where(
            OprReport.project_id == project_id,
            OprReport.report_date == report_date,
            OprReport.author_id == author_id,
        )
        .options(*_REPORT_LOAD)
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
        .options(*_REPORT_LOAD)
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
        .options(*_REPORT_LOAD)
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
    for row in body.rows:
        doc_ids.update(row.doc_ids)
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
            doc_id=row.doc_id if row.doc_id is not None else (row.doc_ids[0] if row.doc_ids else None),
            doc_links=[
                OprRowDoc(doc_id=doc_id)
                for doc_id in dict.fromkeys(
                    ([row.doc_id] if row.doc_id is not None else []) + list(row.doc_ids)
                )
            ],
            source=row.source,
            sort_order=index,
        )
        for index, row in enumerate(body.rows)
    )

    if body.ai_records is not None:
        # 관계 컬렉션으로 붙이므로 신규 OPR 이라도 report_id 를 미리 만들 필요가 없다
        opr_ai_service.apply_records(db, report, ctx.project.id, body.ai_records)

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


# ── AI 사용 기록 ────────────────────────────────────────────────────
# 경로는 relations 라우터의 /opr/reports/{report_id}/docs/{doc_id} 규칙을 따른다.
# 같은 데이터를 PUT /{report_date} 의 ai_records 로도 통째 저장할 수 있다.
# 조회는 프로젝트 멤버면 가능(팀 OPR 화면), 생성·수정·삭제는 OPR 작성자만 가능.


@router.get("/reports/{report_id}/ai-records", response_model=list[OprAiRecordResponse])
def list_ai_records(
    report_id: int,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    return opr_ai_service.list_records(db, ctx, report_id)


@router.post(
    "/reports/{report_id}/ai-records", response_model=OprAiRecordResponse, status_code=201
)
def create_ai_record(
    report_id: int,
    body: OprAiRecordInput,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    return opr_ai_service.create_record(db, ctx, report_id, body)


@router.patch("/reports/{report_id}/ai-records/{record_id}", response_model=OprAiRecordResponse)
def update_ai_record(
    report_id: int,
    record_id: int,
    body: OprAiRecordUpdate,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    return opr_ai_service.update_record(db, ctx, report_id, record_id, body)


@router.delete("/reports/{report_id}/ai-records/{record_id}", status_code=204)
def delete_ai_record(
    report_id: int,
    record_id: int,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    opr_ai_service.delete_record(db, ctx, report_id, record_id)
