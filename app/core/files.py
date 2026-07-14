"""파일 업로드 공통 유틸 — 용량(20MB)·확장자·MIME 검증, UUID 저장명, 경로 조작 방지."""
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.errors import AppError, ErrorCode, bad_request, not_found

ALLOWED_EXTENSIONS = {"pdf", "docx", "xlsx", "pptx", "zip", "png", "jpg", "jpeg"}
_CHUNK = 1024 * 1024

# 확장자별 허용 MIME (브라우저별 편차를 고려해 octet-stream 허용)
_EXT_MIME = {
    "pdf": {"application/pdf"},
    "docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    "xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    "pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
    "zip": {"application/zip", "application/x-zip-compressed"},
    "png": {"image/png"},
    "jpg": {"image/jpeg"},
    "jpeg": {"image/jpeg"},
}
_GENERIC_MIMES = {"application/octet-stream", None, ""}


@dataclass
class StoredFile:
    file_name: str  # 원본명
    stored_name: str  # UUID 저장명 (하위 디렉터리 포함 상대 경로)
    file_size: int
    mime_type: str


def _upload_root() -> Path:
    root = Path(settings.upload_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_upload(file: UploadFile, subdir: str) -> StoredFile:
    """검증 후 로컬 디스크에 저장. 실패 시 부분 파일 제거."""
    original = os.path.basename(file.filename or "")
    if not original or "." not in original:
        raise bad_request(ErrorCode.INVALID_FILE_TYPE, "파일명 또는 확장자가 유효하지 않습니다.")
    ext = original.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise bad_request(ErrorCode.INVALID_FILE_TYPE, f"허용되지 않는 확장자입니다: {ext}")
    content_type = (file.content_type or "").lower()
    if content_type not in _GENERIC_MIMES and content_type not in _EXT_MIME[ext]:
        raise bad_request(ErrorCode.INVALID_FILE_TYPE, f"허용되지 않는 MIME 타입입니다: {content_type}")

    root = _upload_root()
    directory = root / subdir
    directory.mkdir(parents=True, exist_ok=True)
    stored_name = f"{subdir}/{uuid.uuid4().hex}.{ext}"
    dest = (root / stored_name).resolve()
    if not str(dest).startswith(str(root)):  # 경로 조작 방지
        raise bad_request(ErrorCode.INVALID_FILE_TYPE, "잘못된 파일 경로입니다.")

    size = 0
    try:
        with open(dest, "wb") as out:
            while chunk := file.file.read(_CHUNK):
                size += len(chunk)
                if size > settings.max_file_size:
                    raise AppError(413, ErrorCode.FILE_TOO_LARGE, "파일 크기는 20MB를 초과할 수 없습니다.")
                out.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    mime = content_type if content_type not in _GENERIC_MIMES else next(iter(_EXT_MIME[ext]))
    return StoredFile(file_name=original, stored_name=stored_name, file_size=size, mime_type=mime)


def delete_stored_file(stored_name: str) -> None:
    """트랜잭션 실패 시 파일 롤백용. (정책상 삭제 시 물리 파일은 보관하므로 롤백 전용)"""
    (_upload_root() / stored_name).unlink(missing_ok=True)


def stream_download(stored_name: str, file_name: str, mime_type: str) -> FileResponse:
    """스트리밍 다운로드 + Content-Disposition 원본명 복원."""
    path = (_upload_root() / stored_name).resolve()
    if not str(path).startswith(str(_upload_root())) or not path.is_file():
        raise not_found("파일을 찾을 수 없습니다.")
    return FileResponse(path, media_type=mime_type, filename=file_name)
