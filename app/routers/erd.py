import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import ProjectContext, get_project_context
from app.core.errors import AppError, ErrorCode, conflict
from app.core.security import TOKEN_TYPE_ACCESS, decode_token
from app.db.base import utcnow
from app.db.session import SessionLocal, get_db
from app.models import ErdDocument, Project, ProjectMember, User
from app.schemas.collaboration import ErdOut, ErdUpdate
from app.services.erd_hub import ErdPeer, erd_hub

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/erd", tags=["ERD"])


def _normalize_dt(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _same_revision(server: datetime, client: datetime) -> bool:
    return _normalize_dt(server) == _normalize_dt(client)


def _get_or_create_document(db: Session, project_id: int) -> ErdDocument:
    document = db.get(ErdDocument, project_id)
    if document is None:
        document = ErdDocument(project_id=project_id)
        db.add(document)
        db.commit()
        db.refresh(document)
    return document


def _erd_payload(document: ErdDocument) -> dict:
    updated = document.updated_at
    updated_at = updated.isoformat() if isinstance(updated, datetime) else updated
    return {
        "projectId": document.project_id,
        "dbml": document.dbml,
        "positions": document.positions or {},
        "zoom": document.zoom,
        "splitPercent": document.split_percent,
        "updatedAt": updated_at,
    }


async def _broadcast_erd(
    project_id: int,
    document: ErdDocument,
    *,
    client_id: str | None = None,
    event_type: str = "erd-updated",
) -> None:
    await erd_hub.broadcast(
        project_id,
        {
            "type": event_type,
            "clientId": client_id,
            "document": _erd_payload(document),
        },
        exclude_client_id=client_id,
    )


@router.get("", response_model=ErdOut)
def get_erd(ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    return _get_or_create_document(db, ctx.project.id)


@router.put("", response_model=ErdOut)
async def update_erd(
    body: ErdUpdate,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    document = _get_or_create_document(db, ctx.project.id)
    fields_set = body.model_fields_set

    if "base_updated_at" in fields_set and body.base_updated_at is not None:
        if not _same_revision(document.updated_at, body.base_updated_at):
            raise conflict(
                ErrorCode.ERD_CONFLICT,
                "다른 사용자가 먼저 수정했습니다. 최신 ERD를 불러온 뒤 다시 시도하세요.",
            )

    if "dbml" in fields_set and body.dbml is not None:
        document.dbml = body.dbml
    if "positions" in fields_set and body.positions is not None:
        document.positions = body.positions
    if "zoom" in fields_set and body.zoom is not None:
        document.zoom = body.zoom
    if "split_percent" in fields_set and body.split_percent is not None:
        document.split_percent = body.split_percent

    document.updated_at = utcnow()
    db.commit()
    db.refresh(document)
    await _broadcast_erd(ctx.project.id, document, client_id=body.client_id)
    return document


@router.websocket("/ws")
async def erd_ws(
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
        await erd_hub.join(
            project_id,
            ErdPeer(websocket=websocket, client_id=client_id, user_id=user.id),
        )
        joined = True

        document = _get_or_create_document(db, project_id)
        await websocket.send_text(
            json.dumps(
                {
                    "type": "ready",
                    "projectId": project_id,
                    "clientId": client_id,
                    "document": _erd_payload(document),
                },
                ensure_ascii=False,
                default=str,
            )
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

            if msg_type == "erd-state":
                # PUT 전 즉시 중계 (메타만 / 본문 포함)
                doc = message.get("document") or {}
                await erd_hub.broadcast(
                    project_id,
                    {
                        "type": "erd-state",
                        "clientId": client_id,
                        "userId": user.id,
                        "document": {
                            "projectId": project_id,
                            "dbml": doc.get("dbml"),
                            "positions": doc.get("positions"),
                            "splitPercent": doc.get("splitPercent"),
                            "updatedAt": message.get("ts"),
                        },
                    },
                    exclude_client_id=client_id,
                )
                continue

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("erd ws error project=%s", project_id)
    finally:
        db.close()
        if joined:
            await erd_hub.leave(project_id, client_id)
