import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import ProjectContext, get_project_context, require_editor
from app.core.errors import AppError, ErrorCode, conflict
from app.core.security import TOKEN_TYPE_ACCESS, decode_token
from app.db.base import utcnow
from app.db.session import SessionLocal, get_db
from app.models import Project, ProjectMember, User, WhiteboardBoard
from app.models.project import CollabPermission, MemberRole
from app.schemas.collaboration import WhiteboardOut, WhiteboardUpdate
from app.services.whiteboard_hub import WhiteboardPeer, whiteboard_hub

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/whiteboard", tags=["Whiteboard"])


def _normalize_dt(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _same_revision(server: datetime, client: datetime) -> bool:
    return _normalize_dt(server) == _normalize_dt(client)


def _get_or_create_board(db: Session, project_id: int) -> WhiteboardBoard:
    board = db.get(WhiteboardBoard, project_id)
    if board is None:
        board = WhiteboardBoard(project_id=project_id)
        db.add(board)
        db.commit()
        db.refresh(board)
    return board


def _board_payload(board: WhiteboardBoard) -> dict:
    updated = board.updated_at
    if isinstance(updated, datetime):
        updated_at = updated.isoformat()
    else:
        updated_at = updated
    return {
        "projectId": board.project_id,
        "objects": board.objects or [],
        "sizeKey": board.size_key,
        "customWidth": board.custom_width,
        "customHeight": board.custom_height,
        "zoom": board.zoom,
        "updatedAt": updated_at,
    }


async def _broadcast_board(
    project_id: int,
    board: WhiteboardBoard,
    *,
    client_id: str | None = None,
    event_type: str = "board-updated",
) -> None:
    await whiteboard_hub.broadcast(
        project_id,
        {
            "type": event_type,
            "clientId": client_id,
            "board": _board_payload(board),
        },
        exclude_client_id=client_id,
    )


@router.get("", response_model=WhiteboardOut)
def get_whiteboard(ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    return _get_or_create_board(db, ctx.project.id)


@router.put("", response_model=WhiteboardOut)
async def update_whiteboard(
    body: WhiteboardUpdate,
    ctx: ProjectContext = Depends(require_editor),
    db: Session = Depends(get_db),
):
    board = _get_or_create_board(db, ctx.project.id)

    if body.base_updated_at is not None and not _same_revision(board.updated_at, body.base_updated_at):
        raise conflict(
            ErrorCode.WHITEBOARD_CONFLICT,
            "다른 사용자가 먼저 수정했습니다. 최신 화이트보드를 불러온 뒤 다시 시도하세요.",
        )

    board.objects = body.objects
    board.size_key = body.size_key
    board.custom_width = body.custom_width
    board.custom_height = body.custom_height
    board.zoom = body.zoom
    board.updated_at = utcnow()
    db.commit()
    db.refresh(board)
    await _broadcast_board(ctx.project.id, board, client_id=body.client_id)
    return board


@router.post("/reset", response_model=WhiteboardOut)
async def reset_whiteboard(
    ctx: ProjectContext = Depends(require_editor),
    db: Session = Depends(get_db),
    client_id: str | None = Query(default=None),
):
    board = _get_or_create_board(db, ctx.project.id)
    board.objects = []
    board.updated_at = utcnow()
    db.commit()
    db.refresh(board)
    await _broadcast_board(ctx.project.id, board, client_id=client_id)
    return board


@router.websocket("/ws")
async def whiteboard_ws(
    websocket: WebSocket,
    project_id: int,
    token: str = Query(...),
    client_id: str = Query(...),
):
    """화이트보드 실시간 동기화. board-state 중계 + REST 저장 후 board-updated 브로드캐스트."""
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
        peer = WhiteboardPeer(websocket=websocket, client_id=client_id, user_id=user.id)
        await whiteboard_hub.join(project_id, peer)
        joined = True

        board = _get_or_create_board(db, project_id)
        await websocket.send_text(
            json.dumps(
                {
                    "type": "ready",
                    "projectId": project_id,
                    "clientId": client_id,
                    "board": _board_payload(board),
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

            if msg_type == "board-state":
                if member.role != MemberRole.LEADER and member.collab_permission == CollabPermission.VIEWER:
                    continue
                # 로컬 persist 직후 즉시 중계 (PUT 완료 전에도 상대가 볼 수 있음)
                objects = message.get("objects")
                if not isinstance(objects, list):
                    continue
                meta = message.get("meta") or {}
                await whiteboard_hub.broadcast(
                    project_id,
                    {
                        "type": "board-state",
                        "clientId": client_id,
                        "userId": user.id,
                        "board": {
                            "projectId": project_id,
                            "objects": objects,
                            "sizeKey": meta.get("sizeKey"),
                            "customWidth": meta.get("customWidth"),
                            "customHeight": meta.get("customHeight"),
                            # zoom은 뷰포트 — 공유하지 않음
                            "updatedAt": message.get("ts"),
                        },
                    },
                    exclude_client_id=client_id,
                )
                continue

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("whiteboard ws error project=%s", project_id)
    finally:
        db.close()
        if joined:
            await whiteboard_hub.leave(project_id, client_id)
