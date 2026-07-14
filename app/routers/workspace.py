import json
import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import ProjectContext, get_current_user, get_project_context
from app.core.errors import AppError, conflict, forbidden, not_found
from app.core.security import TOKEN_TYPE_ACCESS, decode_token
from app.db.session import SessionLocal, get_db
from app.models import Project, ProjectMember, User, WorkspaceFile, WorkspaceFileVersion
from app.schemas.collaboration import (
    WorkspaceFileCreate,
    WorkspaceFileOut,
    WorkspaceFileRestore,
    WorkspaceFileUpdate,
    WorkspaceFileVersionOut,
)
from app.services.workspace_hub import WorkspacePeer, workspace_hub

logger = logging.getLogger(__name__)

project_router = APIRouter(prefix="/api/projects/{project_id}/workspace", tags=["Workspace"])
file_router = APIRouter(prefix="/api/workspace/files", tags=["Workspace"])


def _require_file_member(db: Session, project_id: int, user_id: int) -> None:
    member = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user_id
        )
    )
    if member is None:
        raise forbidden("프로젝트 멤버가 아닙니다.")


def _get_file_or_404(db: Session, file_id: int) -> WorkspaceFile:
    file = db.get(WorkspaceFile, file_id)
    if file is None:
        raise not_found("파일을 찾을 수 없습니다.")
    return file


def _append_version(db: Session, file: WorkspaceFile, user_id: int) -> None:
    db.add(
        WorkspaceFileVersion(
            file_id=file.id,
            version=file.version,
            content=file.content,
            saved_by=user_id,
        )
    )


@project_router.get("/files", response_model=list[WorkspaceFileOut])
def list_workspace_files(
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(WorkspaceFile)
        .where(WorkspaceFile.project_id == ctx.project.id)
        .order_by(WorkspaceFile.path.asc())
    ).all()


@project_router.post("/files", response_model=WorkspaceFileOut, status_code=201)
def create_workspace_file(
    body: WorkspaceFileCreate,
    ctx: ProjectContext = Depends(get_project_context),
    db: Session = Depends(get_db),
):
    existing = db.scalar(
        select(WorkspaceFile).where(
            WorkspaceFile.project_id == ctx.project.id, WorkspaceFile.path == body.path
        )
    )
    if existing is not None:
        raise conflict("DUPLICATE_PATH", "이미 같은 경로의 파일이 있습니다.")

    file = WorkspaceFile(
        project_id=ctx.project.id,
        path=body.path,
        language=body.language or "plaintext",
        content=body.content,
        version=1,
        updated_by=ctx.user.id,
    )
    db.add(file)
    db.flush()
    _append_version(db, file, ctx.user.id)
    db.commit()
    db.refresh(file)
    return file


@file_router.put("/{file_id}", response_model=WorkspaceFileOut)
def update_workspace_file(
    file_id: int,
    body: WorkspaceFileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    file = _get_file_or_404(db, file_id)
    _require_file_member(db, file.project_id, user.id)
    file.content = body.content
    file.version += 1
    file.updated_by = user.id
    _append_version(db, file, user.id)
    db.commit()
    db.refresh(file)
    return file


@file_router.delete("/{file_id}", status_code=204)
def delete_workspace_file(
    file_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    file = _get_file_or_404(db, file_id)
    _require_file_member(db, file.project_id, user.id)
    db.delete(file)
    db.commit()


@file_router.get("/{file_id}/versions", response_model=list[WorkspaceFileVersionOut])
def list_workspace_file_versions(
    file_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    file = _get_file_or_404(db, file_id)
    _require_file_member(db, file.project_id, user.id)
    return db.scalars(
        select(WorkspaceFileVersion)
        .where(WorkspaceFileVersion.file_id == file_id)
        .order_by(WorkspaceFileVersion.version.desc())
    ).all()


@file_router.post("/{file_id}/restore", response_model=WorkspaceFileOut)
def restore_workspace_file_version(
    file_id: int,
    body: WorkspaceFileRestore,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    file = _get_file_or_404(db, file_id)
    _require_file_member(db, file.project_id, user.id)

    version = db.get(WorkspaceFileVersion, body.version_id)
    if version is None or version.file_id != file_id:
        raise not_found("버전을 찾을 수 없습니다.")

    file.content = version.content
    file.version += 1
    file.updated_by = user.id
    _append_version(db, file, user.id)
    db.commit()
    db.refresh(file)
    return file


@project_router.websocket("/ws")
async def workspace_ws(
    websocket: WebSocket,
    project_id: int,
    token: str = Query(...),
    client_id: str = Query(...),
):
    """편집 중 실시간 동기화 + presence. 토큰은 query 로 전달."""
    db = SessionLocal()
    peer: WorkspacePeer | None = None
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
        peer = WorkspacePeer(
            websocket=websocket,
            user_id=user.id,
            nickname=user.nickname,
            client_id=client_id,
        )
        presence = await workspace_hub.join(project_id, peer)
        await websocket.send_text(
            json.dumps(
                {
                    "type": "ready",
                    "projectId": project_id,
                    "clientId": client_id,
                    "presence": presence,
                },
                ensure_ascii=False,
            )
        )
        await workspace_hub.broadcast(
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

            if msg_type == "editing":
                file_id = message.get("fileId")
                try:
                    editing_id = int(file_id) if file_id is not None else None
                except (TypeError, ValueError):
                    editing_id = None
                presence = await workspace_hub.set_editing(project_id, client_id, editing_id)
                await workspace_hub.broadcast(
                    project_id,
                    {"type": "presence", "projectId": project_id, "presence": presence},
                )
                continue

            if msg_type == "content-change":
                file_id = message.get("fileId")
                content = message.get("content")
                if file_id is None or not isinstance(content, str):
                    continue
                try:
                    file_id_int = int(file_id)
                except (TypeError, ValueError):
                    continue
                await workspace_hub.broadcast(
                    project_id,
                    {
                        "type": "content-change",
                        "projectId": project_id,
                        "fileId": file_id_int,
                        "content": content,
                        "clientId": client_id,
                        "userId": user.id,
                        "nickname": user.nickname,
                        "ts": message.get("ts"),
                    },
                    exclude_client_id=client_id,
                )
                continue

            if msg_type in {"file-saved", "file-updated", "files-changed"}:
                outbound = {
                    "type": msg_type,
                    "projectId": project_id,
                    "fileId": message.get("fileId"),
                    "content": message.get("content"),
                    "version": message.get("version"),
                    "ts": message.get("ts"),
                    "clientId": client_id,
                    "userId": user.id,
                    "nickname": user.nickname,
                }
                if msg_type != "files-changed":
                    try:
                        outbound["fileId"] = int(message["fileId"])
                    except (KeyError, TypeError, ValueError):
                        continue
                await workspace_hub.broadcast(
                    project_id,
                    outbound,
                    exclude_client_id=client_id,
                )
                continue

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("workspace ws error project=%s", project_id)
    finally:
        db.close()
        if peer is not None:
            presence = await workspace_hub.leave(project_id, client_id)
            await workspace_hub.broadcast(
                project_id,
                {"type": "presence", "projectId": project_id, "presence": presence},
            )
