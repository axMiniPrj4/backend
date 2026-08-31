"""OPR AI 사용 기록 서비스.

권한 원칙
- 조회는 프로젝트 멤버면 가능하다 (팀 OPR 화면에서 남의 기록도 읽는다).
- 생성·수정·삭제는 그 OPR 의 작성자만 가능하다.
  OPR 본문 저장 자체가 (project_id, report_date, author_id) 로 본인 것만 열리는 구조라
  같은 기준을 따른다. 팀장이라도 남의 학습 기록을 고칠 수는 없다.

연결 검증
- WBS/자료 모두 "같은 프로젝트인가"만 본다. 소프트 삭제된 대상도 허용하는데,
  기존 OPR 저장(routers/opr.py:_validate_linked_resources)이 같은 이유로 그렇게 한다.
  이미 저장된 기록을 다시 저장할 때 대상이 삭제됐다는 이유로 실패하면 안 되기 때문이다.
"""
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import ProjectContext
from app.core.errors import bad_request, forbidden, not_found
from app.models import Doc, OprReport, Task
from app.models.opr_ai import OprAiRecord, OprAiRecordDoc, OprAiRecordProvider, OprAiRecordTask
from app.schemas.opr_ai import OprAiRecordInput, OprAiRecordUpdate

_RECORD_LOAD = (
    selectinload(OprAiRecord.providers),
    selectinload(OprAiRecord.task_links),
    selectinload(OprAiRecord.doc_links),
)


def _get_report(db: Session, ctx: ProjectContext, report_id: int) -> OprReport:
    report = db.scalar(
        select(OprReport).where(
            OprReport.id == report_id, OprReport.project_id == ctx.project.id
        )
    )
    if report is None:
        raise not_found("OPR을 찾을 수 없습니다.")
    return report


def _require_author(ctx: ProjectContext, report: OprReport) -> None:
    if report.author_id != ctx.user.id:
        raise forbidden("본인이 작성한 OPR의 AI 기록만 수정할 수 있습니다.")


def _get_record(db: Session, report: OprReport, record_id: int) -> OprAiRecord:
    record = db.scalar(
        select(OprAiRecord)
        .where(OprAiRecord.id == record_id, OprAiRecord.report_id == report.id)
        .options(*_RECORD_LOAD)
    )
    if record is None:
        raise not_found("AI 사용 기록을 찾을 수 없습니다.")
    return record


def validate_task_ids(db: Session, project_id: int, task_ids: list[int]) -> None:
    if not task_ids:
        return
    wanted = set(task_ids)
    found = set(
        db.scalars(
            select(Task.id)
            .where(Task.project_id == project_id, Task.id.in_(wanted))
            .execution_options(include_deleted=True)
        )
    )
    if found != wanted:
        raise bad_request(message="이 프로젝트의 WBS 작업만 연결할 수 있습니다.")


def validate_doc_ids(db: Session, project_id: int, doc_ids: list[int]) -> None:
    if not doc_ids:
        return
    wanted = set(doc_ids)
    found = set(
        db.scalars(
            select(Doc.id)
            .where(
                Doc.id.in_(wanted),
                or_(Doc.project_id == project_id, Doc.project_id.is_(None)),
            )
            .execution_options(include_deleted=True)
        )
    )
    if found != wanted:
        raise bad_request(message="이 프로젝트의 자료 또는 공통 자료만 연결할 수 있습니다.")


def _set_providers(record: OprAiRecord, providers) -> None:
    record.providers.clear()
    record.providers.extend(
        OprAiRecordProvider(
            provider=item.provider,
            custom_provider_name=item.custom_provider_name,
        )
        for item in providers
    )


def _set_task_links(record: OprAiRecord, task_ids: list[int]) -> None:
    record.task_links.clear()
    record.task_links.extend(OprAiRecordTask(task_id=task_id) for task_id in task_ids)


def _set_doc_links(record: OprAiRecord, doc_ids: list[int]) -> None:
    record.doc_links.clear()
    record.doc_links.extend(OprAiRecordDoc(doc_id=doc_id) for doc_id in doc_ids)


def _fill(record: OprAiRecord, data: OprAiRecordInput) -> None:
    record.title = data.title
    record.question = data.question
    record.answer_summary = data.answer_summary
    record.application_result = data.application_result
    record.lesson_learned = data.lesson_learned
    record.artifact_link = data.artifact_link
    record.sort_order = data.sort_order
    _set_providers(record, data.providers)
    _set_task_links(record, data.task_ids)
    _set_doc_links(record, data.doc_ids)


def list_records(db: Session, ctx: ProjectContext, report_id: int) -> list[OprAiRecord]:
    report = _get_report(db, ctx, report_id)
    return list(
        db.scalars(
            select(OprAiRecord)
            .where(OprAiRecord.report_id == report.id)
            .options(*_RECORD_LOAD)
            .order_by(OprAiRecord.sort_order.asc(), OprAiRecord.id.asc())
        ).all()
    )


def create_record(
    db: Session, ctx: ProjectContext, report_id: int, data: OprAiRecordInput
) -> OprAiRecord:
    report = _get_report(db, ctx, report_id)
    _require_author(ctx, report)
    validate_task_ids(db, ctx.project.id, data.task_ids)
    validate_doc_ids(db, ctx.project.id, data.doc_ids)

    record = OprAiRecord(report_id=report.id, author_id=report.author_id)
    _fill(record, data)
    db.add(record)
    db.commit()
    return _get_record(db, report, record.id)


def update_record(
    db: Session, ctx: ProjectContext, report_id: int, record_id: int, data: OprAiRecordUpdate
) -> OprAiRecord:
    report = _get_report(db, ctx, report_id)
    _require_author(ctx, report)
    record = _get_record(db, report, record_id)

    if data.task_ids is not None:
        validate_task_ids(db, ctx.project.id, data.task_ids)
    if data.doc_ids is not None:
        validate_doc_ids(db, ctx.project.id, data.doc_ids)

    for field in (
        "title",
        "question",
        "answer_summary",
        "application_result",
        "lesson_learned",
        "artifact_link",
        "sort_order",
    ):
        value = getattr(data, field)
        # answer_summary 등 선택 항목을 비우려면 빈 문자열을 보내면 된다(검증에서 None 으로 정규화).
        # 아예 키를 보내지 않으면 기존 값을 유지한다.
        if field in data.model_fields_set:
            setattr(record, field, value)

    if data.providers is not None:
        _set_providers(record, data.providers)
    if data.task_ids is not None:
        _set_task_links(record, data.task_ids)
    if data.doc_ids is not None:
        _set_doc_links(record, data.doc_ids)

    db.commit()
    return _get_record(db, report, record.id)


def delete_record(db: Session, ctx: ProjectContext, report_id: int, record_id: int) -> None:
    report = _get_report(db, ctx, report_id)
    _require_author(ctx, report)
    record = _get_record(db, report, record_id)
    # providers / task_links / doc_links 는 delete-orphan 으로 함께 지워진다.
    db.delete(record)
    db.commit()


def apply_records(
    db: Session, report: OprReport, project_id: int, inputs: list[OprAiRecordInput]
) -> None:
    """OPR 통째 저장(PUT)에서 호출. 커밋은 호출자가 한다.

    id 가 있으면 갱신, 없으면 생성, 목록에 없는 기존 기록은 삭제한다.
    opr_row 처럼 전부 지우고 다시 만들면 저장할 때마다 기록 id 가 바뀌어
    상세보기·연결이 끊기므로 id 를 보존한다.

    구현 메모: 세션에 직접 delete 를 걸면 이미 로드된 report.ai_records 컬렉션과
    어긋나 삭제가 반영되지 않는다. delete-orphan 이 걸린 컬렉션을 통째로 교체해
    빠진 항목이 고아로 정리되게 한다.
    """
    all_task_ids: list[int] = []
    all_doc_ids: list[int] = []
    for item in inputs:
        all_task_ids.extend(item.task_ids)
        all_doc_ids.extend(item.doc_ids)
    validate_task_ids(db, project_id, list(dict.fromkeys(all_task_ids)))
    validate_doc_ids(db, project_id, list(dict.fromkeys(all_doc_ids)))

    existing = {record.id: record for record in report.ai_records}

    next_records: list[OprAiRecord] = []
    for index, item in enumerate(inputs):
        target = existing.get(item.id) if item.id is not None else None
        if item.id is not None and target is None:
            raise not_found("수정할 AI 사용 기록을 찾을 수 없습니다.")
        if target is None:
            target = OprAiRecord(author_id=report.author_id)
        _fill(target, item)
        # 목록 순서를 그대로 정렬 순서로 쓴다 (sort_order 를 클라이언트가 안 보내도 동작)
        target.sort_order = index
        next_records.append(target)

    report.ai_records[:] = next_records
