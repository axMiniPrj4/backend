"""파일 업로드 공통 유틸 — 용량·확장자·MIME 검증, UUID 저장명, 경로 조작 방지."""
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.errors import AppError, ErrorCode, bad_request, not_found

# 팀 자료실용 — 문서·이미지·압축·텍스트 위주 (.exe 등 실행파일 제외)
ALLOWED_EXTENSIONS = {
    # 문서
    "pdf",
    "doc",
    "docx",
    "txt",
    "md",
    "rtf",
    "hwp",
    "hwpx",
    # 스프레드시트
    "xls",
    "xlsx",
    "csv",
    # 발표
    "ppt",
    "pptx",
    # 이미지
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
    "bmp",
    "svg",
    # 압축
    "zip",
    "7z",
    "rar",
    # 데이터/마크업
    "json",
    "xml",
    "html",
    "htm",
}
_CHUNK = 1024 * 1024

# 확장자별 허용 MIME (브라우저별 편차 → octet-stream 허용)
_EXT_MIME = {
    "pdf": {"application/pdf"},
    "doc": {"application/msword"},
    "docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    "txt": {"text/plain"},
    "md": {"text/plain", "text/markdown"},
    "rtf": {"application/rtf", "text/rtf"},
    "hwp": {"application/x-hwp", "application/haansofthwp"},
    "hwpx": {"application/hwp+zip", "application/vnd.hancom.hwpx"},
    "xls": {"application/vnd.ms-excel"},
    "xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    "csv": {"text/csv", "text/plain", "application/csv"},
    "ppt": {"application/vnd.ms-powerpoint"},
    "pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
    "png": {"image/png"},
    "jpg": {"image/jpeg"},
    "jpeg": {"image/jpeg"},
    "gif": {"image/gif"},
    "webp": {"image/webp"},
    "bmp": {"image/bmp", "image/x-ms-bmp"},
    "svg": {"image/svg+xml"},
    "zip": {"application/zip", "application/x-zip-compressed"},
    "7z": {"application/x-7z-compressed"},
    "rar": {"application/vnd.rar", "application/x-rar-compressed"},
    "json": {"application/json", "text/plain"},
    "xml": {"application/xml", "text/xml"},
    "html": {"text/html"},
    "htm": {"text/html"},
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
    allowed_mimes = _EXT_MIME.get(ext, set())
    if content_type not in _GENERIC_MIMES and content_type not in allowed_mimes:
        raise bad_request(ErrorCode.INVALID_FILE_TYPE, f"허용되지 않는 MIME 타입입니다: {content_type}")

    root = _upload_root()
    directory = root / subdir
    directory.mkdir(parents=True, exist_ok=True)
    stored_name = f"{subdir}/{uuid.uuid4().hex}.{ext}"
    dest = (root / stored_name).resolve()
    if not str(dest).startswith(str(root)):  # 경로 조작 방지
        raise bad_request(ErrorCode.INVALID_FILE_TYPE, "잘못된 파일 경로입니다.")

    max_mb = max(1, settings.max_file_size // (1024 * 1024))
    size = 0
    try:
        with open(dest, "wb") as out:
            while chunk := file.file.read(_CHUNK):
                size += len(chunk)
                if size > settings.max_file_size:
                    raise AppError(
                        413,
                        ErrorCode.FILE_TOO_LARGE,
                        f"파일 크기는 {max_mb}MB를 초과할 수 없습니다.",
                    )
                out.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    mime = (
        content_type
        if content_type not in _GENERIC_MIMES
        else next(iter(allowed_mimes or {"application/octet-stream"}))
    )
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
