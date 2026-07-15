"""Refresh Token 저장소 — Redis (TTL = RT 만료). REDIS_URL 미설정 시 인메모리 폴백(개발 전용)."""
import threading
import time

from app.core.config import settings

_RT_KEY = "rt:{user_id}"


class InMemoryTokenStore:
    def __init__(self):
        self._data: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        with self._lock:
            self._data[key] = (value, time.monotonic() + ttl_seconds)

    def get(self, key: str) -> str | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            value, expires = item
            if time.monotonic() > expires:
                del self._data[key]
                return None
            return value

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)


class RedisTokenStore:
    def __init__(self, url: str):
        import redis

        self._client = redis.Redis.from_url(url, decode_responses=True)

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._client.set(key, value, ex=ttl_seconds)

    def get(self, key: str) -> str | None:
        return self._client.get(key)

    def delete(self, key: str) -> None:
        self._client.delete(key)


_store = RedisTokenStore(settings.redis_url) if settings.redis_url else InMemoryTokenStore()


def save_refresh_token(user_id: int, token: str) -> None:
    _store.set(_RT_KEY.format(user_id=user_id), token, settings.refresh_token_expire_days * 86400)


def get_refresh_token(user_id: int) -> str | None:
    return _store.get(_RT_KEY.format(user_id=user_id))


def delete_refresh_token(user_id: int) -> None:
    _store.delete(_RT_KEY.format(user_id=user_id))


_RESET_KEY = "pwdreset:{token}"


def save_password_reset_token(token: str, user_id: int) -> None:
    ttl = max(60, int(settings.password_reset_token_minutes) * 60)
    _store.set(_RESET_KEY.format(token=token), str(user_id), ttl)


def pop_password_reset_token(token: str) -> int | None:
    key = _RESET_KEY.format(token=token)
    raw = _store.get(key)
    if raw is None:
        return None
    _store.delete(key)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
