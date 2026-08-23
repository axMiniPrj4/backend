from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import ProjectContext, get_project_context
from app.db.session import get_db
from app.schemas.relation import DocRelationsOut, OprRelationsOut, RelationLinkOut, TaskRelationsOut
from app.services.relation_service import (
    get_doc_relations,
    get_opr_relations,
    get_task_relations,
    link_opr_doc,
    link_task_doc,
    unlink_opr_doc,
    unlink_task_doc,
)

router = APIRouter(prefix="/api/projects/{project_id}", tags=["Relations"])


@router.get("/tasks/{task_id}/relations", response_model=TaskRelationsOut)
def task_relations(task_id: int, ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    return get_task_relations(db, ctx, task_id)


@router.post("/tasks/{task_id}/docs/{doc_id}", response_model=RelationLinkOut)
def add_task_doc(task_id: int, doc_id: int, ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    return link_task_doc(db, ctx, task_id, doc_id)


@router.delete("/tasks/{task_id}/docs/{doc_id}", status_code=204)
def remove_task_doc(task_id: int, doc_id: int, ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    unlink_task_doc(db, ctx, task_id, doc_id)


@router.get("/opr/reports/{report_id}/relations", response_model=OprRelationsOut)
def opr_relations(report_id: int, ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    return get_opr_relations(db, ctx, report_id)


@router.post("/opr/reports/{report_id}/docs/{doc_id}", response_model=RelationLinkOut)
def add_opr_doc(report_id: int, doc_id: int, ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    return link_opr_doc(db, ctx, report_id, doc_id)


@router.delete("/opr/reports/{report_id}/docs/{doc_id}", status_code=204)
def remove_opr_doc(report_id: int, doc_id: int, ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    unlink_opr_doc(db, ctx, report_id, doc_id)


@router.get("/docs/{doc_id}/relations", response_model=DocRelationsOut)
def doc_relations(doc_id: int, ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    return get_doc_relations(db, ctx, doc_id)
