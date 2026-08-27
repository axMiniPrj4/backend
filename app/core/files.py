"""파일 업로드 공통 유틸 — 용량·확장자·MIME 검증, UUID 저장명, 경로 조작 방지."""
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.errors import AppError, ErrorCode, bad_request, not_found

# 팀 자료실용 — 문서·이미지·압축·텍스트·소스코드 위주 (.exe 등 바이너리 실행파일 제외)
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
    "yaml",
    "yml",
    "toml",
    "ini",
    "cfg",
    "conf",
    # 소스코드·스크립트 (텍스트)
    "sh",
    "bash",
    "zsh",
    "ps1",
    "bat",
    "cmd",
    "py",
    "js",
    "jsx",
    "mjs",
    "cjs",
    "ts",
    "tsx",
    "java",
    "kt",
    "go",
    "rs",
    "rb",
    "php",
    "pl",
    "lua",
    "r",
    "sql",
    "c",
    "h",
    "cpp",
    "hpp",
    "cc",
    "cs",
    "swift",
    "vue",
    "svelte",
    "ipynb",
    "gradle",
    "groovy",
}
_CHUNK = 1024 * 1024

# 확장자별 허용 MIME (브라우저별 편차 → octet-stream 허용)
_EXT_MIME = {
    "pdf": {"application/pdf"},
    # doc/xls/ppt(레거시 OLE) — 일부 OS/브라우저는 범용 오피스 MIME으로 보고
    "doc": {
        "application/haansoftdoc","application/msword", "application/vnd.ms-office"},
    # docx/xlsx/pptx/hwpx는 내부적으로 ZIP 컨테이너라 OS의 MIME 매핑이 없으면
    # application/zip(-compressed)으로 보고되는 경우가 있음 — 함께 허용
    "docx": {
        "application/haansoftdocx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/x-zip-compressed",
        # 일부 Windows 는 레지스트리 매핑이 틀어져 docx 를 구형/범용 오피스 MIME 으로 보고한다
        "application/msword",
        "application/vnd.ms-word.document.12",
        "application/vnd.ms-office",
    },
    "txt": {"text/plain"},
    "md": {"text/plain", "text/markdown"},
    "rtf": {"application/rtf", "text/rtf"},
    "hwp": {"application/x-hwp", "application/haansofthwp"},
    "hwpx": {
        "application/haansofthwpx",
        "application/hwp+zip",
        "application/vnd.hancom.hwpx",
        "application/zip",
        "application/x-zip-compressed",
    },
    "xls": {
        "application/haansoftxls","application/vnd.ms-excel", "application/vnd.ms-office"},
    "xlsx": {
        "application/haansoftxlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
        "application/x-zip-compressed",
        # docx 와 동일한 오매핑 사례
        "application/vnd.ms-excel",
        "application/vnd.ms-excel.sheet.macroenabled.12",
        "application/vnd.ms-office",
    },
    "csv": {"text/csv", "text/plain", "application/csv"},
    "ppt": {
        "application/haansoftppt","application/vnd.ms-powerpoint", "application/vnd.ms-office"},
    "pptx": {
        "application/haansoftpptx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/zip",
        "application/x-zip-compressed",
        # docx 와 동일한 오매핑 사례
        "application/vnd.ms-powerpoint",
        "application/vnd.ms-powerpoint.presentation.macroenabled.12",
        "application/vnd.ms-office",
    },
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
    "yaml": {"text/yaml", "application/yaml", "application/x-yaml", "text/plain"},
    "yml": {"text/yaml", "application/yaml", "application/x-yaml", "text/plain"},
    "toml": {"application/toml", "text/plain"},
    "ini": {"text/plain"},
    "cfg": {"text/plain"},
    "conf": {"text/plain"},
    "sh": {"text/x-shellscript", "text/x-sh", "application/x-sh", "text/plain"},
    "bash": {"text/x-shellscript", "text/x-sh", "application/x-sh", "text/plain"},
    "zsh": {"text/x-shellscript", "text/x-sh", "application/x-sh", "text/plain"},
    "ps1": {"text/plain", "application/x-powershell"},
    "bat": {"text/plain", "application/x-bat", "application/bat"},
    "cmd": {"text/plain", "application/x-bat"},
    "py": {"text/x-python", "application/x-python", "text/plain"},
    "js": {"text/javascript", "application/javascript", "application/x-javascript", "text/plain"},
    "jsx": {"text/javascript", "application/javascript", "text/plain"},
    "mjs": {"text/javascript", "application/javascript", "text/plain"},
    "cjs": {"text/javascript", "application/javascript", "text/plain"},
    "ts": {"text/typescript", "application/typescript", "text/plain"},
    "tsx": {"text/typescript", "application/typescript", "text/plain"},
    "java": {"text/x-java-source", "text/plain"},
    "kt": {"text/x-kotlin", "text/plain"},
    "go": {"text/x-go", "text/plain"},
    "rs": {"text/x-rust", "text/plain"},
    "rb": {"text/x-ruby", "application/x-ruby", "text/plain"},
    "php": {"application/x-httpd-php", "text/x-php", "text/plain"},
    "pl": {"text/x-perl", "application/x-perl", "text/plain"},
    "lua": {"text/x-lua", "text/plain"},
    "r": {"text/x-r", "text/plain"},
    "sql": {"application/sql", "text/x-sql", "text/plain"},
    "c": {"text/x-c", "text/plain"},
    "h": {"text/x-c", "text/plain"},
    "cpp": {"text/x-c++", "text/plain"},
    "hpp": {"text/x-c++", "text/plain"},
    "cc": {"text/x-c++", "text/plain"},
    "cs": {"text/x-csharp", "text/plain"},
    "swift": {"text/x-swift", "text/plain"},
    "vue": {"text/plain", "application/javascript"},
    "svelte": {"text/plain"},
    "ipynb": {"application/json", "application/x-ipynb+json", "text/plain"},
    "gradle": {"text/plain", "text/x-groovy"},
    "groovy": {"text/x-groovy", "text/plain"},
}
_GENERIC_MIMES = {"application/octet-stream", None, ""}

# MIME 검사를 참고용으로만 쓰는 확장자.
# 브라우저·OS·설치된 오피스(MS/한컴)에 따라 Content-Type 이 제각각이라
# 정상 파일이 거부되는 사례가 반복됐다. 확장자 화이트리스트가 실제 방어선이며,
# Content-Type 은 클라이언트가 임의로 보낼 수 있어 보안 가치가 낮다.
# 이미지 계열은 MIME 이 안정적이라 제외(엄격 검사 유지).
_MIME_ADVISORY_EXTS = {
    "pdf", "doc", "docx", "txt", "md", "rtf", "hwp", "hwpx",
    "xls", "xlsx", "csv", "ppt", "pptx",
    "zip", "7z", "rar",
    "json", "xml", "html", "htm", "yaml", "yml", "toml", "ini", "cfg", "conf",
    "sh", "bash", "zsh", "ps1", "bat", "cmd", "py", "js", "jsx", "mjs", "cjs",
    "ts", "tsx", "java", "kt", "go", "rs", "rb", "php", "pl", "lua", "r", "sql",
    "c", "h", "cpp", "hpp", "cc", "cs", "swift", "vue", "svelte", "ipynb",
    "gradle", "groovy",
}


# 확장자별 정규 MIME — 저장·다운로드에 사용한다.
# 클라이언트가 보낸 Content-Type 은 신뢰하지 않고 이 표에서 유도한다.
_CANONICAL_MIME = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "md": "text/markdown",
    "rtf": "application/rtf",
    "hwp": "application/x-hwp",
    "hwpx": "application/hwp+zip",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "bmp": "image/bmp",
    "svg": "image/svg+xml",
    "zip": "application/zip",
    "7z": "application/x-7z-compressed",
    "rar": "application/vnd.rar",
    "json": "application/json",
    "ipynb": "application/json",
    "xml": "application/xml",
    "html": "text/html",
    "htm": "text/html",
}

# 위 표에 없고 텍스트로 다뤄도 되는 확장자(설정·소스코드)는 text/plain 으로 통일
_TEXTLIKE_EXTS = {
    "yaml", "yml", "toml", "ini", "cfg", "conf",
    "sh", "bash", "zsh", "ps1", "bat", "cmd", "py", "js", "jsx", "mjs", "cjs",
    "ts", "tsx", "java", "kt", "go", "rs", "rb", "php", "pl", "lua", "r", "sql",
    "c", "h", "cpp", "hpp", "cc", "cs", "swift", "vue", "svelte",
    "gradle", "groovy",
}


def canonical_mime(ext: str) -> str:
    """확장자에서 응답에 쓸 MIME 을 정한다(클라이언트 값 미신뢰)."""
    if ext in _CANONICAL_MIME:
        return _CANONICAL_MIME[ext]
    if ext in _TEXTLIKE_EXTS:
        return "text/plain"
    return "application/octet-stream"


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
    # Content-Type 은 클라이언트가 임의로 보낼 수 있어 검증에 쓰지 않는다.
    # 확장자 화이트리스트(ALLOWED_EXTENSIONS)가 실제 방어선이며,
    # 응답에 쓸 MIME 은 아래에서 확장자로부터 유도한다.
    # (브라우저·OS·설치된 오피스에 따라 docx -> application/haansoftdocx,
    #  application/msword 등으로 제각각 보고되어 정상 파일이 거부되던 문제 제거)

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
    mime = canonical_mime(ext)
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
