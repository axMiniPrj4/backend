import json
import logging
import sys
import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.handlers import register_exception_handlers
from app.routers import (
    activities,
    admin,
    ai,
    archive,
    auth,
    calendar,
    chat,
    docs,
    erd,
    inquiries,
    members,
    notices,
    project_todos,
    projects,
    task_comments,
    tasks,
    todos,
    users,
    video,
    whiteboard,
    workspace,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    force=True,
)
logger = logging.getLogger("app.request")
logger.setLevel(logging.INFO)
# uvicorn 기본 로거에도 보이도록
logging.getLogger("uvicorn.error").setLevel(logging.INFO)
logging.getLogger("uvicorn.access").setLevel(logging.INFO)

_MAX_BODY_LOG = 2000
_SENSITIVE_KEYS = {
    "password",
    "current_password",
    "new_password",
    "refresh_token",
    "access_token",
    "token",
    "image_data",
}


def _redact(value):
    if isinstance(value, list):
        return [_redact(v) for v in value]
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if str(k).lower() in _SENSITIVE_KEYS:
                if isinstance(v, str) and v:
                    out[k] = f"***({len(v)})"
                else:
                    out[k] = "***"
            else:
                out[k] = _redact(v)
        return out
    return value


def _format_body(raw: bytes, content_type: str | None) -> str:
    if not raw:
        return "(empty)"
    text = raw.decode("utf-8", errors="replace")
    if content_type and "application/json" in content_type:
        try:
            text = json.dumps(_redact(json.loads(text)), ensure_ascii=False)
        except Exception:
            pass
    if len(text) > _MAX_BODY_LOG:
        return text[:_MAX_BODY_LOG] + f"...(+{len(text) - _MAX_BODY_LOG} chars)"
    return text


def _safe_stdout(message: str) -> None:
    """Windows cp949 콘솔에서도 이모지 등으로 깨지지 않게 출력 (실패해도 요청은 유지)."""
    try:
        print(message, flush=True)
        return
    except UnicodeEncodeError:
        pass
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        safe = message.encode(encoding, errors="backslashreplace").decode(encoding, errors="replace")
        print(safe, flush=True)
    except Exception:
        pass


app = FastAPI(title=settings.app_name, version="1.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    start = time.perf_counter()
    path = request.url.path
    log_bodies = path.startswith("/api")

    req_body = b""
    if log_bodies and request.method in {"POST", "PUT", "PATCH"}:
        req_body = await request.body()

        async def receive():
            return {"type": "http.request", "body": req_body, "more_body": False}

        request = Request(request.scope, receive)

    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000

    if not log_bodies:
        logger.info("%s %s -> %d (%.1fms)", request.method, path, response.status_code, elapsed_ms)
        return response

    resp_chunks: list[bytes] = []
    async for chunk in response.body_iterator:
        resp_chunks.append(chunk)
    resp_body = b"".join(resp_chunks)

    req_ct = request.headers.get("content-type")
    resp_ct = response.headers.get("content-type")
    logger.info(
        "%s %s -> %d (%.1fms)\n  SEND ↑ %s\n  RECV ↓ %s",
        request.method,
        path,
        response.status_code,
        elapsed_ms,
        _format_body(req_body, req_ct) if req_body or request.method in {"POST", "PUT", "PATCH"} else "(no body)",
        _format_body(resp_body, resp_ct),
    )
    # reload 자식 프로세스에서도 확실히 보이게 stdout에 한 줄 더
    # (이모지 등 비-cp949 문자가 있어도 요청 자체는 실패하지 않도록)
    _safe_stdout(
        f"[API] {request.method} {path} -> {response.status_code} ({elapsed_ms:.1f}ms)\n"
        f"  SEND ↑ {_format_body(req_body, req_ct) if req_body or request.method in {'POST', 'PUT', 'PATCH'} else '(no body)'}\n"
        f"  RECV ↓ {_format_body(resp_body, resp_ct)}"
    )

    headers = dict(response.headers)
    headers.pop("content-length", None)
    return Response(
        content=resp_body,
        status_code=response.status_code,
        headers=headers,
        media_type=response.media_type,
        background=response.background,
    )


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(projects.router)
app.include_router(members.router)
app.include_router(tasks.router)
app.include_router(task_comments.router)
app.include_router(todos.router)
app.include_router(project_todos.router)
app.include_router(docs.router)
app.include_router(archive.router)
app.include_router(inquiries.router)
app.include_router(notices.router)
app.include_router(activities.router)
app.include_router(chat.router)
app.include_router(whiteboard.router)
app.include_router(erd.router)
app.include_router(workspace.project_router)
app.include_router(workspace.file_router)
app.include_router(video.router)
app.include_router(ai.router)
app.include_router(calendar.router)
app.include_router(admin.router)
