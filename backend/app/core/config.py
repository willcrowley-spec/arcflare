from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/arcflare",
        description="Async SQLAlchemy URL (asyncpg driver).",
    )
    DATABASE_URL_SYNC: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/arcflare",
        description="Sync URL for Alembic (psycopg2).",
    )
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    CLERK_SECRET_KEY: str = Field(default="")
    CLERK_PUBLISHABLE_KEY: str = Field(default="")
    CLERK_ISSUER: str | None = Field(
        default=None,
        description="JWT issuer (e.g. https://your-instance.clerk.accounts.dev).",
    )
    CLERK_JWKS_URL: str | None = Field(
        default=None,
        description="Override JWKS URL; defaults to {issuer}/.well-known/jwks.json",
    )

    OPENAI_API_KEY: str = Field(default="")
    ANTHROPIC_API_KEY: str = Field(default="")
    GEMINI_API_KEY: str = Field(default="")

    LLM_PROVIDER: str = Field(default="anthropic", description="openai, anthropic, or gemini")
    LLM_LITE_MODEL: str = Field(default="")
    LLM_FAST_MODEL: str = Field(default="")
    LLM_STRONG_MODEL: str = Field(default="")
    LLM_RATE_DELAY: float = Field(default=0.0, description="Seconds between LLM calls")

    SALESFORCE_CLIENT_ID: str = Field(default="")
    SALESFORCE_CLIENT_SECRET: str = Field(default="")
    SALESFORCE_REDIRECT_URI: str = Field(
        default="http://localhost:8000/api/v1/connections/salesforce/callback"
    )

    ENCRYPTION_KEY: str = Field(
        default="",
        description="Fernet key (url-safe base64 32-byte).",
    )

    FRONTEND_URL: str = Field(default="http://localhost:3000")
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"

    CORS_ORIGINS: str = Field(
        default="http://localhost:3000",
        description="Comma-separated list of allowed CORS origins.",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def split_origins(cls, v: str | list[str]) -> str:
        if isinstance(v, list):
            return ",".join(v)
        return v

    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
