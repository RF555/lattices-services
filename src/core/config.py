"""Application configuration using Pydantic Settings."""

from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="Lattices API")
    app_env: str = Field(default="development")
    debug: bool = Field(default=False)

    # Server
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://localhost:5432/lattices",
        description="PostgreSQL connection URL with asyncpg driver",
    )

    # For testing with SQLite
    test_database_url: str = Field(
        default="sqlite+aiosqlite:///./test.db",
        description="Test database URL",
    )

    # Supabase
    supabase_url: str = Field(
        default="",
        description="Supabase project URL (e.g. https://xyzabc.supabase.co)",
    )
    supabase_anon_key: str = Field(
        default="",
        description="Supabase anonymous/public API key",
    )
    supabase_service_role_key: str = Field(
        default="",
        description="Supabase service role key (server-side only, keep secret)",
    )

    # JWT Authentication
    jwt_secret_key: str = Field(
        default="CHANGE-ME-IN-PRODUCTION",
        description="Secret key for JWT signing (used for HS256 fallback and tests)",
    )
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=30)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def supabase_jwks_url(self) -> str:
        """JWKS endpoint for ES256 token verification."""
        if self.supabase_url:
            return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        return ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def async_database_url(self) -> str:
        """Ensure the database URL uses the asyncpg driver scheme.

        Render and other providers supply a standard ``postgresql://`` URL.
        SQLAlchemy's async engine requires ``postgresql+asyncpg://``.
        """
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    # Rate Limiting
    rate_limit_enabled: bool = Field(
        default=True,
        description="Enable/disable rate limiting (disable for tests)",
    )

    # CORS
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        description="Comma-separated list of allowed origins",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.app_env == "production"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
