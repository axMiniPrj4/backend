from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import ProjectContext, get_project_context
from app.db.session import get_db
from app.models import ChatMessage
from app.schemas.collaboration import ChatMessageCreate, ChatMessageOut

router = APIRouter(prefix="/api/projects/{project_id}/chat", tags=["Chat"])


@router.get("/messages", response_model=list[ChatMessageOut])
def list_chat_messages(
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(ChatMessage)
        .where(ChatMessage.project_id == ctx.project.id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
    ).all()


@router.post("/messages", response_model=ChatMessageOut, status_code=201)
def create_chat_message(
    body: ChatMessageCreate,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    message = ChatMessage(
        project_id=ctx.project.id,
        author_id=ctx.user.id,
        type=body.type,
        content=body.content,
        image_data=body.image_data,
        file_name=body.file_name,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message
