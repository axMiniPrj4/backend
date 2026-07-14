from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings
from app.core.errors import ErrorCode, unauthorized

TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


def _create_token(user_id: int, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int) -> str:
    return _create_token(user_id, TOKEN_TYPE_ACCESS, timedelta(minutes=settings.access_token_expire_minutes))


def create_refresh_token(user_id: int) -> str:
    return _create_token(user_id, TOKEN_TYPE_REFRESH, timedelta(days=settings.refresh_token_expire_days))


def decode_token(token: str, expected_type: str) -> int:
    """토큰 검증 후 user_id 반환. 실패 시 401 AppError."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise unauthorized(ErrorCode.TOKEN_EXPIRED, "토큰이 만료되었습니다.")
    except jwt.InvalidTokenError:
        raise unauthorized(ErrorCode.INVALID_TOKEN, "유효하지 않은 토큰입니다.")
    if payload.get("type") != expected_type:
        raise unauthorized(ErrorCode.INVALID_TOKEN, "유효하지 않은 토큰입니다.")
    try:
        return int(payload["sub"])
    except (KeyError, ValueError):
        raise unauthorized(ErrorCode.INVALID_TOKEN, "유효하지 않은 토큰입니다.")
