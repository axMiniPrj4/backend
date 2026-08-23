"""DB 세션 — 기본 DB 장애 시 선택적 보조 DB로 부팅·런타임 전환."""
from __future__ import annotations

import threading
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_lock = threading.Lock()
_using_rds = False
engine: Engine
SessionLocal: sessionmaker


def _connect_args_for(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    # DB 네트워크 장애 시 요청이 길게 매달리지 않도록 짧게 유지한다.
    return {"connect_timeout": 3}


def _make_engine(url: str) -> Engine:
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args=_connect_args_for(url),
    )


def _probe(eng: Engine) -> None:
    with eng.connect() as conn:
        conn.execute(text("SELECT 1"))


def _is_connectivity_error(exc: BaseException) -> bool:
    if isinstance(exc, (OperationalError, InterfaceError)):
        return True
    msg = str(exc).lower()
    needles = (
        "can't connect",
        "timed out",
        "timeout",
        "connection refused",
        "lost connection",
        "gone away",
        "server has gone away",
        "not connected",
    )
    return any(n in msg for n in needles)


def _build_engine() -> Engine:
    """기동 시 기본 DB에 연결하고, 실패하면 설정된 보조 DB로 전환한다."""
    global _using_rds
    try:
        primary = _make_engine(settings.database_url)
        _probe(primary)
        print("[DB] 기본 DB 연결 성공")
        _using_rds = False
        return primary
    except OperationalError as e:
        print(f"[DB] 기본 DB 연결 실패: {e}")

    if not settings.rds_database_url:
        raise Exception("기본 DB 연결에 실패했고, 보조 DB 주소도 설정되어 있지 않습니다.")

    backup = _make_engine(settings.rds_database_url)
    try:
        _probe(backup)
    except OperationalError as e:
        print(f"[DB] 보조 DB 연결도 실패: {e}")
        raise
    print("[DB] 보조 DB로 전환 성공 (부팅)")
    _using_rds = True
    return backup


def failover_to_rds(reason: BaseException | None = None) -> bool:
    """런타임에 기본 DB 장애 시 보조 DB로 교체한다. 이미 전환됐거나 URL이 없으면 False."""
    global engine, SessionLocal, _using_rds
    if not settings.rds_database_url:
        return False

    with _lock:
        if _using_rds:
            return False

        print(f"[DB] 런타임 장애 감지 → 보조 DB 전환 시도: {reason}")
        try:
            backup = _make_engine(settings.rds_database_url)
            _probe(backup)
        except Exception as e:
            print(f"[DB] 런타임 보조 DB 전환 실패: {e}")
            return False

        old = engine
        engine = backup
        SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        _using_rds = True
        try:
            old.dispose()
        except Exception:
            pass
        print("[DB] 런타임 보조 DB로 전환 성공")
        return True


def is_using_rds() -> bool:
    return _using_rds


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db: Session = SessionLocal()
    try:
        try:
            # pool_pre_ping + 즉시 checkout으로 끊어진 DB 연결을 여기서 감지한다.
            db.connection()
        except Exception as e:
            db.close()
            if _is_connectivity_error(e) and failover_to_rds(e):
                db = SessionLocal()
                db.connection()
            else:
                raise
        yield db
    finally:
        db.close()
