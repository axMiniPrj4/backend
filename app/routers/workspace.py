from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import ProjectContext, get_current_user, get_project_context
from app.core.errors import conflict, forbidden, not_found
from app.db.session import get_db
from app.models import ProjectMember, User, WorkspaceFile, WorkspaceFileVersion
from app.schemas.collaboration import (
    WorkspaceFileCreate,
    WorkspaceFileOut,
    WorkspaceFileRestore,
    WorkspaceFileUpdate,
    WorkspaceFileVersionOut,
)

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
