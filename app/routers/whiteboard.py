from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import ProjectContext, get_project_context
from app.db.session import get_db
from app.models import WhiteboardBoard
from app.schemas.collaboration import WhiteboardOut, WhiteboardUpdate

router = APIRouter(prefix="/api/projects/{project_id}/whiteboard", tags=["Whiteboard"])


def _get_or_create_board(db: Session, project_id: int) -> WhiteboardBoard:
    board = db.get(WhiteboardBoard, project_id)
    if board is None:
        board = WhiteboardBoard(project_id=project_id)
        db.add(board)
        db.commit()
        db.refresh(board)
    return board


@router.get("", response_model=WhiteboardOut)
def get_whiteboard(ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    return _get_or_create_board(db, ctx.project.id)


@router.put("", response_model=WhiteboardOut)
def update_whiteboard(
    body: WhiteboardUpdate,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    board = _get_or_create_board(db, ctx.project.id)
    board.objects = body.objects
    board.size_key = body.size_key
    board.custom_width = body.custom_width
    board.custom_height = body.custom_height
    board.zoom = body.zoom
    db.commit()
    db.refresh(board)
    return board


@router.post("/reset", response_model=WhiteboardOut)
def reset_whiteboard(ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    board = _get_or_create_board(db, ctx.project.id)
    board.objects = []
    db.commit()
    db.refresh(board)
    return board
