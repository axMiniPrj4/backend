from time import time
from threading import Lock

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import ProjectContext, get_project_context
from app.db.base import utcnow
from app.db.session import get_db
from app.models import VideoSession
from app.schemas.collaboration import (
    VideoPeerIn,
    VideoPeerOut,
    VideoSessionOut,
    VideoSessionUpdate,
    VideoSignalIn,
    VideoSignalOut,
)

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
