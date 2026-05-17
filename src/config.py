import os
from functools import lru_cache
from typing import Literal
from urllib.parse import unquote, urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

# Parse AWS_BEDROCK_CONN (Airflow-style URL) into AWS_* env vars when set.
# Permite reusar o secret `airflow-connections-aws_bedrock` que o projeto DGB
# já mantém em Secret Manager. Formato:
#   aws://ACCESS_KEY:SECRET_KEY@/?region_name=us-east-1
_aws_conn_raw = os.environ.get("AWS_BEDROCK_CONN")
if _aws_conn_raw:
    try:
        _parsed = urlparse(_aws_conn_raw)
        os.environ.setdefault("AWS_ACCESS_KEY_ID", unquote(_parsed.username or ""))
        os.environ.setdefault("AWS_SECRET_ACCESS_KEY", unquote(_parsed.password or ""))
        _qs = dict(p.split("=") for p in (_parsed.query or "").split("&") if "=" in p)
        os.environ.setdefault("AWS_DEFAULT_REGION", _qs.get("region_name", "us-east-1"))
    except Exception:
        pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: Literal["development", "demo", "production"] = "development"

    def is_demo(self) -> bool:
        return self.ENVIRONMENT == "demo"

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
