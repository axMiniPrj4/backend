"""에러 코드 상수 + 앱 공통 예외 (명세 3-3)."""


class ErrorCode:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_FILE_TYPE = "INVALID_FILE_TYPE"
    INVALID_DATE_RANGE = "INVALID_DATE_RANGE"
    INVALID_PLAN = "INVALID_PLAN"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    INVALID_TOKEN = "INVALID_TOKEN"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    INVALID_PROJECT_CODE = "INVALID_PROJECT_CODE"
    DUPLICATE_LOGIN_ID = "DUPLICATE_LOGIN_ID"
    DUPLICATE_EMAIL = "DUPLICATE_EMAIL"
    DUPLICATE_NICKNAME = "DUPLICATE_NICKNAME"
    ALREADY_JOINED = "ALREADY_JOINED"
    LEADER_CANNOT_LEAVE = "LEADER_CANNOT_LEAVE"
    LEADER_PROJECT_EXISTS = "LEADER_PROJECT_EXISTS"
    ALREADY_ANSWERED = "ALREADY_ANSWERED"
    ANSWER_EXISTS = "ANSWER_EXISTS"
    LAST_VERSION_CANNOT_DELETE = "LAST_VERSION_CANNOT_DELETE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    ERD_CONFLICT = "ERD_CONFLICT"
    WHITEBOARD_CONFLICT = "WHITEBOARD_CONFLICT"
    MAIL_NOT_CONFIGURED = "MAIL_NOT_CONFIGURED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str, detail=None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(message)


def bad_request(code: str = ErrorCode.VALIDATION_ERROR, message: str = "유효하지 않은 요청입니다.", detail=None) -> AppError:
    return AppError(400, code, message, detail)


def unauthorized(code: str = ErrorCode.INVALID_TOKEN, message: str = "인증이 필요합니다.") -> AppError:
    return AppError(401, code, message)


def forbidden(message: str = "권한이 없습니다.") -> AppError:
    return AppError(403, ErrorCode.FORBIDDEN, message)


def not_found(message: str = "리소스를 찾을 수 없습니다.", code: str = ErrorCode.NOT_FOUND) -> AppError:
    return AppError(404, code, message)


def conflict(code: str, message: str) -> AppError:
    return AppError(409, code, message)
