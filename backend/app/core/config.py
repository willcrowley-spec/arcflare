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
    CEREBRAS_API_KEY: str = Field(default="")

    LLM_PROVIDER: str = Field(default="cerebras", description="openai, anthropic, gemini, or cerebras")
    LLM_LITE_MODEL: str = Field(default="")
    LLM_FAST_MODEL: str = Field(default="")
    LLM_STRONG_MODEL: str = Field(default="")
    LLM_RATE_DELAY: float = Field(default=0.0, description="Seconds between LLM calls")
    RECOMMENDATION_DOMAIN_CONCURRENCY: int = Field(
        default=4,
        ge=1,
        le=12,
        description="Maximum number of domain recommendation analyses to run in parallel.",
    )
    PROCESS_DISCOVERY_DOMAIN_CONCURRENCY: int = Field(
        default=8,
        ge=1,
        le=24,
        description="Maximum number of process-discovery domain extraction/verification calls to run in parallel.",
    )

    EMBEDDING_MODEL: str = Field(default="gemini-embedding-2-preview", description="Gemini embedding model name")
    EMBEDDING_DIMS: int = Field(default=768, description="Embedding vector dimensions (MRL-truncated from 3072)")

    SERPAPI_KEY: str = Field(default="", description="SerpAPI key for org research web search")

    SALESFORCE_CLIENT_ID: str = Field(default="")
    SALESFORCE_CLIENT_SECRET: str = Field(default="")
    SALESFORCE_REDIRECT_URI: str = Field(
        default="http://localhost:8000/api/v1/connections/salesforce/callback"
    )
    SALESFORCE_DEV_HUB_ALIAS: str = Field(
        default="elevate-prod",
        description="Salesforce CLI alias for optional Agentforce scratch org validation.",
    )
    AGENTFORCE_SCRATCH_VALIDATION_ENABLED: bool = Field(
        default=False,
        description="Feature flag for creating scratch orgs from generated agent source bundles.",
    )

    ENCRYPTION_KEY: str = Field(
        default="",
        description="Fernet key (url-safe base64 32-byte).",
    )

    FRONTEND_URL: str = Field(default="http://localhost:3000")
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"

    LANGFUSE_SECRET_KEY: str = Field(default="")
    LANGFUSE_PUBLIC_KEY: str = Field(default="")
    LANGFUSE_BASE_URL: str = Field(default="https://cloud.langfuse.com")

    ARC_AGENT_NAME: str = Field(default="Arc", description="Display name for the chat agent")

    ARCBRAIN_CODEGRAPH_ENABLED: bool = Field(
        default=False,
        description="Enable optional Arcbrain code graph ingestion via a configured provider.",
    )
    ARCBRAIN_CODEGRAPH_PROVIDER: Literal["none", "codebase_memory"] = Field(
        default="none",
        description="Code graph provider for Arcbrain.",
    )
    ARCBRAIN_CODEGRAPH_BINARY: str = Field(
        default="codebase-memory-mcp",
        description="Path or executable name for the codebase-memory-mcp binary.",
    )
    ARCBRAIN_CODEGRAPH_REPOS: str = Field(
        default="",
        description="Semicolon-separated repo list, e.g. arcflare=/app;client=/workspace/client.",
    )
    ARCBRAIN_CODEGRAPH_MODE: str = Field(
        default="fast",
        description="codebase-memory-mcp indexing mode: fast, moderate, or full.",
    )
    ARCBRAIN_CODEGRAPH_TIMEOUT_SECONDS: int = Field(
        default=45,
        ge=5,
        le=300,
        description="Timeout per codebase-memory-mcp CLI call.",
    )
    ARCBRAIN_CODEGRAPH_CACHE_TTL_SECONDS: int = Field(
        default=300,
        ge=0,
        le=3600,
        description="In-process cache TTL for Arcbrain code graph projections.",
    )

    S3_BUCKET: str = Field(default="", description="Railway Bucket name (S3-compatible)")
    S3_ACCESS_KEY_ID: str = Field(default="", alias="AWS_ACCESS_KEY_ID")
    S3_SECRET_ACCESS_KEY: str = Field(default="", alias="AWS_SECRET_ACCESS_KEY")
    S3_ENDPOINT: str = Field(default="https://storage.railway.app", description="S3 endpoint URL")
    S3_REGION: str = Field(default="auto", alias="AWS_DEFAULT_REGION")

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
