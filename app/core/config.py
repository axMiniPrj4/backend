from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ohapjijol.io"
    debug: bool = False

    # DB (MySQL 8 기준. 로컬 개발/테스트는 sqlite URL 사용 가능)
    database_url: str = "mysql+pymysql://ohap:ohap@localhost:3306/ohapjijol?charset=utf8mb4"

    # 1차 DB(라즈베리파이) 연결 실패 시 우회할 2차 DB(RDS). 미설정("") 시 우회 없이 그대로 실패
    rds_database_url: str = ""

    # Redis: 미설정("") 시 인메모리 토큰 저장소로 폴백 (개발 전용)
    redis_url: str = ""

    # JWT — 기준안 #1: Access 30분 / Refresh 7일 / RT 응답 body / 미회전
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # 파일 업로드
    upload_dir: str = "./uploads"
    max_file_size: int = 50 * 1024 * 1024  # 50MB

    # CORS
    cors_origins: str = "*"  # 콤마 구분 목록

    # AI (선택) — 미설정 시 가응답
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    # SMTP (아이디 찾기·비밀번호 재설정 메일). SMTP_HOST 비우면 메일 비활성
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    frontend_base_url: str = "http://localhost:5173"
    password_reset_token_minutes: int = 60

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def mail_enabled(self) -> bool:
        return bool(self.smtp_host.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
