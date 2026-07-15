from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def _connect_args_for(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {"connect_timeout": 3}


def _build_engine():
    # 1차: 원래 DB(라즈베리파이)로 연결 시도
    try:
        primary_engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            connect_args=_connect_args_for(settings.database_url),
        )
        with primary_engine.connect():
            pass
        primary_engine.dispose()  # 확인용 커넥션이 풀에 남아 파일/커넥션을 붙잡지 않도록 정리
        print("[DB] 1차 DB(라즈베리파이) 연결 성공")
        return primary_engine
    except OperationalError as e:
        print(f"[DB] 1차 DB 연결 실패: {e}")

    # 2차: RDS로 전환
    if settings.rds_database_url:
        try:
            backup_engine = create_engine(
                settings.rds_database_url,
                pool_pre_ping=True,
                connect_args=_connect_args_for(settings.rds_database_url),
            )
            with backup_engine.connect():
                pass
            backup_engine.dispose()
            print("[DB] 2차 DB(RDS)로 전환 성공")
            return backup_engine
        except OperationalError as e:
            print(f"[DB] 2차 DB(RDS) 연결도 실패: {e}")
            raise
    else:
        raise Exception("1차 DB 연결 실패했고, RDS 주소도 설정되어 있지 않습니다.")


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
