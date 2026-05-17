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

    # AWS Bedrock — feature "Reescrever com IA" no registro de execução
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_DEFAULT_REGION: str = "us-east-1"
    BEDROCK_MODEL_ID: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    BEDROCK_MAX_RETRIES: int = 3
    BEDROCK_MAX_TOKENS: int = 1500
    AI_REWRITE_RATE_LIMIT_PER_HOUR: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
