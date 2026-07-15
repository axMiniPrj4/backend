import json
import logging
from time import time
from threading import Lock

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import ProjectContext, get_project_context
from app.core.errors import AppError
from app.core.security import TOKEN_TYPE_ACCESS, decode_token
from app.db.base import utcnow
from app.db.session import SessionLocal, get_db
from app.models import Project, ProjectMember, User, VideoSession
from app.schemas.collaboration import (
    VideoPeerIn,
    VideoPeerOut,
    VideoSessionOut,
    VideoSessionUpdate,
    VideoSignalIn,
    VideoSignalOut,
)
from app.services.video_hub import VideoPeerConn, video_hub

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/video", tags=["Video"])

# 인메모리 peer 목록 + WebRTC 시그널 우편함 (단일 프로세스)
_PEER_LOCK = Lock()
_PEERS: dict[int, dict[str, dict]] = {}
_SIGNALS: dict[int, dict[str, list[dict]]] = {}
_PEER_STALE_SEC = 25.0


def _get_or_create_session(db: Session, project_id: int) -> VideoSession:
    session = db.get(VideoSession, project_id)
    if session is None:
        session = VideoSession(project_id=project_id)
        db.add(session)
        db.commit()
        db.refresh(session)
    return session


def _purge_stale(project_id: int) -> None:
    bucket = _PEERS.get(project_id)
    if not bucket:
        return
    now = time()
    stale = [pid for pid, info in bucket.items() if now - info.get("ts", 0) > _PEER_STALE_SEC]
    for pid in stale:
        del bucket[pid]
        inbox = _SIGNALS.get(project_id)
        if inbox:
            inbox.pop(pid, None)
    if not bucket:
        _PEERS.pop(project_id, None)
        _SIGNALS.pop(project_id, None)


def _peers_out(project_id: int) -> list[VideoPeerOut]:
    with _PEER_LOCK:
        _purge_stale(project_id)
        bucket = _PEERS.get(project_id, {})
        return [
            VideoPeerOut(
                peer_id=pid,
                nickname=info.get("nickname") or "",
                muted=bool(info.get("muted")),
                camera_off=bool(info.get("camera_off")),
            )
            for pid, info in bucket.items()
        ]


def _sync_session_live_flag(db: Session, project_id: int) -> VideoSession:
    session = _get_or_create_session(db, project_id)
    peers = _peers_out(project_id)
    live = len(peers) > 0
    session.joined = live
    if live and session.started_at is None:
        session.started_at = utcnow()
    if not live:
        session.started_at = None
        session.muted = False
        session.camera_off = False
    db.commit()
    db.refresh(session)
    return session


@router.get("", response_model=VideoSessionOut)
def get_video_session(ctx: ProjectContext = Depends(get_project_context), db: Session = Depends(get_db)):
    return _sync_session_live_flag(db, ctx.project.id)


@router.put("", response_model=VideoSessionOut)
def update_video_session(
    body: VideoSessionUpdate,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    session = _get_or_create_session(db, ctx.project.id)
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(session, field, value)
    db.commit()
    db.refresh(session)
    return session


@router.get("/live-peers")
async def list_live_video_peers(ctx: ProjectContext = Depends(get_project_context)):
    """WebRTC WS 허브에 실제로 접속 중인 peer 목록 (로비용)."""
    _ = ctx
    peers = await video_hub.list_peers(ctx.project.id)
    return {"peers": peers, "count": len(peers)}


@router.get("/peers", response_model=list[VideoPeerOut])
def list_video_peers(ctx: ProjectContext = Depends(get_project_context)):
    return _peers_out(ctx.project.id)


@router.put("/peers", response_model=VideoPeerOut)
def upsert_video_peer(
    body: VideoPeerIn,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    project_id = ctx.project.id
    with _PEER_LOCK:
        bucket = _PEERS.setdefault(project_id, {})
        bucket[body.peer_id] = {
            "nickname": body.nickname,
            "muted": body.muted,
            "camera_off": body.camera_off,
            "user_id": ctx.user.id,
            "ts": time(),
        }
    _sync_session_live_flag(db, project_id)
    return VideoPeerOut(
        peer_id=body.peer_id,
        nickname=body.nickname,
        muted=body.muted,
        camera_off=body.camera_off,
    )


@router.delete("/peers/{peer_id}", status_code=204)
def remove_video_peer(
    peer_id: str,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    project_id = ctx.project.id
    with _PEER_LOCK:
        bucket = _PEERS.get(project_id)
        if bucket and peer_id in bucket:
            del bucket[peer_id]
            if not bucket:
                _PEERS.pop(project_id, None)
        inbox = _SIGNALS.get(project_id)
        if inbox:
            inbox.pop(peer_id, None)
            # bye to remaining peers
            for target, messages in inbox.items():
                messages.append(
                    {
                        "from_peer_id": peer_id,
                        "type": "bye",
                        "payload": {},
                    }
                )
    _sync_session_live_flag(db, project_id)


@router.post("/signals", response_model=VideoSignalOut, status_code=201)
def post_video_signal(
    body: VideoSignalIn,
    ctx: ProjectContext = Depends(get_project_context),
    from_peer_id: str = Query(..., min_length=1, max_length=120),
):
    project_id = ctx.project.id
    message = {
        "from_peer_id": from_peer_id,
        "type": body.type,
        "payload": body.payload or {},
    }
    with _PEER_LOCK:
        bucket = _SIGNALS.setdefault(project_id, {})
        bucket.setdefault(body.to_peer_id, []).append(message)
    return VideoSignalOut(**message)


@router.get("/signals", response_model=list[VideoSignalOut])
def drain_video_signals(
    ctx: ProjectContext = Depends(get_project_context),
    peer_id: str = Query(..., min_length=1, max_length=120),
):
    project_id = ctx.project.id
    with _PEER_LOCK:
        bucket = _SIGNALS.setdefault(project_id, {})
        messages = bucket.get(peer_id, [])
        bucket[peer_id] = []
    return [VideoSignalOut(**m) for m in messages]


def _sync_session_live_flag_ws(project_id: int, live: bool) -> None:
    db = SessionLocal()
    try:
        session = _get_or_create_session(db, project_id)
        session.joined = live
        if live and session.started_at is None:
            session.started_at = utcnow()
        if not live:
            session.started_at = None
            session.muted = False
            session.camera_off = False
        db.commit()
    except Exception:
        logger.exception("video session sync failed project=%s", project_id)
    finally:
        db.close()


@router.websocket("/ws")
async def video_signaling_ws(
    websocket: WebSocket,
    project_id: int,
    token: str = Query(...),
    peer_id: str = Query(..., min_length=1, max_length=120),
    nickname: str = Query(default="", max_length=100),
    muted: bool = Query(default=False),
    camera_off: bool = Query(default=False),
):
    """WebRTC 시그널링 전용 WebSocket — offer/answer/candidate 실시간 중계."""
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
        display_name = (nickname or user.nickname or "").strip() or user.nickname
        peer = VideoPeerConn(
            websocket=websocket,
            peer_id=peer_id,
            user_id=user.id,
            nickname=display_name,
            muted=muted,
            camera_off=camera_off,
        )
        peers = await video_hub.join(project_id, peer)
        joined = True
        _sync_session_live_flag_ws(project_id, True)

        await websocket.send_text(
            json.dumps(
                {
                    "type": "ready",
                    "projectId": project_id,
                    "peerId": peer_id,
                    "peers": [p for p in peers if p["peerId"] != peer_id],
                },
                ensure_ascii=False,
            )
        )
        await video_hub.broadcast(
            project_id,
            {
                "type": "peer-joined",
                "projectId": project_id,
                "peer": {
                    "peerId": peer_id,
                    "nickname": display_name,
                    "muted": muted,
                    "cameraOff": camera_off,
                    "userId": user.id,
                },
            },
            exclude_peer_id=peer_id,
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

            if msg_type == "presence":
                peers = await video_hub.update_meta(
                    project_id,
                    peer_id,
                    nickname=message.get("nickname"),
                    muted=message.get("muted"),
                    camera_off=message.get("cameraOff"),
                    sharing_screen=message.get("sharingScreen"),
                )
                me = next((p for p in peers if p["peerId"] == peer_id), None)
                if me:
                    await video_hub.broadcast(
                        project_id,
                        {"type": "peer-updated", "projectId": project_id, "peer": me},
                        exclude_peer_id=peer_id,
                    )
                continue

            if msg_type == "signal":
                to_peer_id = message.get("toPeerId")
                signal_type = message.get("signalType")
                payload = message.get("payload") or {}
                if not to_peer_id or signal_type not in {"offer", "answer", "candidate", "bye"}:
                    continue
                await video_hub.send_to(
                    project_id,
                    to_peer_id,
                    {
                        "type": "signal",
                        "fromPeerId": peer_id,
                        "signalType": signal_type,
                        "payload": payload,
                    },
                )
                continue

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("video ws error project=%s peer=%s", project_id, peer_id)
    finally:
        db.close()
        if joined:
            peers = await video_hub.leave(project_id, peer_id)
            await video_hub.broadcast(
                project_id,
                {"type": "peer-left", "projectId": project_id, "peerId": peer_id},
            )
            _sync_session_live_flag_ws(project_id, len(peers) > 0)
