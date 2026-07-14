from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import ProjectContext, get_project_context
from app.db.session import get_db
from app.models import ErdDocument
from app.schemas.collaboration import ErdOut, ErdUpdate

router = APIRouter(prefix="/api/projects/{project_id}/erd", tags=["ERD"])


def _get_or_create_document(db: Session, project_id: int) -> ErdDocument:
    document = db.get(ErdDocument, project_id)
    if document is None:
        document = ErdDocument(project_id=project_id)
        db.add(document)
        db.commit()
        db.refresh(document)
    return document


@router.get("", response_model=ErdOut)
def get_erd(ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    return _get_or_create_document(db, ctx.project.id)


@router.put("", response_model=ErdOut)
def update_erd(
    body: ErdUpdate,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    document = _get_or_create_document(db, ctx.project.id)
    document.dbml = body.dbml
    document.positions = body.positions
    document.zoom = body.zoom
    document.split_percent = body.split_percent
    db.commit()
    db.refresh(document)
    return document
