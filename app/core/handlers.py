"""전역 예외 핸들러 — 에러 응답 단일 포맷 {code, message, detail} 강제."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError, ErrorCode

logger = logging.getLogger("app")

_STATUS_TO_CODE = {
    400: ErrorCode.VALIDATION_ERROR,
    401: ErrorCode.INVALID_TOKEN,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.VALIDATION_ERROR,
    413: ErrorCode.FILE_TOO_LARGE,
}


def _error_response(status_code: int, code: str, message: str, detail=None) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"code": code, "message": message, "detail": detail})


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return _error_response(exc.status_code, exc.code, exc.message, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        detail = [
            {
                "loc": ".".join(str(x) for x in e["loc"]),
                "msg": e["msg"],
                "type": e.get("type"),
            }
            for e in exc.errors()
        ]
        return _error_response(400, ErrorCode.VALIDATION_ERROR, "요청 값이 유효하지 않습니다.", detail)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        code = _STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        return _error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error: %s %s", request.method, request.url.path)
        return _error_response(500, ErrorCode.INTERNAL_ERROR, "서버 내부 오류가 발생했습니다.")
