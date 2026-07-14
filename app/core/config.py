from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ohapjijol.io"
    debug: bool = False

    # DB (MySQL 8 기준. 로컬 개발/테스트는 sqlite URL 사용 가능)
    database_url: str = "mysql+pymysql://ohap:ohap@localhost:3306/ohapjijol?charset=utf8mb4"

    # Redis: 미설정("") 시 인메모리 토큰 저장소로 폴백 (개발 전용)
    redis_url: str = ""

    # JWT — 기준안 #1: Access 30분 / Refresh 7일 / RT 응답 body / 미회전
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # 파일 업로드
    upload_dir: str = "./uploads"
    max_file_size: int = 20 * 1024 * 1024  # 20MB

    # CORS
    cors_origins: str = "*"  # 콤마 구분 목록

    # AI (선택) — 미설정 시 가응답
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
