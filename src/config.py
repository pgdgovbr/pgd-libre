from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "development"
    APP_URL: str = "http://localhost:8000"
    SECRET_KEY: str = "dev-insecure-secret-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    FRONTEND_URL: str = "http://localhost:5173"

    DATABASE_URL: str = "postgresql+psycopg://pgdlibre:pgdlibre@localhost:5432/pgdlibre"

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    GOVBR_CLIENT_ID: str = ""
    GOVBR_CLIENT_SECRET: str = ""
    GOVBR_ISSUER: str = "https://sso.acesso.gov.br"

    MAIL_SERVER: str = "localhost"
    MAIL_PORT: int = 1025
    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: str = ""
    MAIL_FROM: str = "pgd-libre@example.gov.br"
    MAIL_STARTTLS: bool = False
    MAIL_SSL_TLS: bool = False

    API_PGD_URL: str = ""
    API_PGD_USERNAME: str = ""
    API_PGD_PASSWORD: str = ""
    SYNC_SECRET: str = "dev-sync-secret"


@lru_cache
def get_settings() -> Settings:
    return Settings()
