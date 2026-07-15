import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import ProjectContext, get_project_context, require_editor
from app.core.errors import AppError
from app.core.security import TOKEN_TYPE_ACCESS, decode_token
from app.db.session import SessionLocal, get_db
from app.models import ChatMessage, Project, ProjectMember, User
from app.schemas.collaboration import ChatMessageCreate, ChatMessageOut
from app.services.chat_hub import ChatPeer, chat_hub

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/chat", tags=["Chat"])


def _message_payload(message: ChatMessage) -> dict:
    created = message.created_at
    created_at = created.isoformat() if isinstance(created, datetime) else created
    return {
        "id": message.id,
        "project_id": message.project_id,
        "author_id": message.author_id,
        "type": message.type,
        "content": message.content,
        "image_data": message.image_data,
        "file_name": message.file_name,
        "created_at": created_at,
    }


async def _broadcast_message(
    project_id: int,
    message: ChatMessage,
    *,
    client_id: str | None = None,
) -> None:
    await chat_hub.broadcast(
        project_id,
        {
            "type": "chat-message",
            "clientId": client_id,
            "message": _message_payload(message),
        },
        exclude_client_id=client_id,
    )


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
async def create_chat_message(
    body: ChatMessageCreate,
    ctx: ProjectContext = Depends(require_editor),
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
    await _broadcast_message(ctx.project.id, message, client_id=body.client_id)
    return message


@router.websocket("/ws")
async def chat_ws(
    websocket: WebSocket,
    project_id: int,
    token: str = Query(...),
    client_id: str = Query(...),
):
    db = SessionLocal()
    joined = False
    try:
        try:
            user_id = decode_token(token, TOKEN_TYPE_ACCESS)
        except AppError:
            await websocket.close(code=4401)
            return

        user = db.get(User, user_id)
        if user is None or user.is_deleted or user.is_suspended:
            await websocket.close(code=4401)
            return

        project = db.get(Project, project_id)
        if project is None or project.is_deleted:
            await websocket.close(code=4404)
            return

        member = db.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id, ProjectMember.user_id == user.id
            )
        )
        if member is None:
            await websocket.close(code=4403)
            return

        await websocket.accept()
        presence = await chat_hub.join(
            project_id,
            ChatPeer(websocket=websocket, client_id=client_id, user_id=user.id, nickname=user.nickname),
        )
        joined = True
        await websocket.send_text(
            json.dumps(
                {"type": "ready", "projectId": project_id, "clientId": client_id, "presence": presence}
            )
        )
        await chat_hub.broadcast(
            project_id,
            {"type": "presence", "projectId": project_id, "presence": presence},
            exclude_client_id=client_id,
        )

        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = message.get("type")
            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue

            if msg_type == "typing":
                presence = await chat_hub.set_typing(project_id, client_id, bool(message.get("typing")))
                await chat_hub.broadcast(
                    project_id,
                    {"type": "presence", "projectId": project_id, "presence": presence},
                    exclude_client_id=client_id,
                )
                continue

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("chat ws error project=%s", project_id)
    finally:
        db.close()
        if joined:
            presence = await chat_hub.leave(project_id, client_id)
            await chat_hub.broadcast(
                project_id,
                {"type": "presence", "projectId": project_id, "presence": presence},
            )
