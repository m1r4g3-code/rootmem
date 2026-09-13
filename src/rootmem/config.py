"""Runtime configuration, loaded from environment variables.

Fails fast at construction time (a required/invalid setting raises immediately)
rather than surfacing as a mysterious failure deep in a tool call later.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    postgres_user: str = "rootmem"
    postgres_password: str = "rootmem_dev_password"
    postgres_db: str = "rootmem"
    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, gt=0, le=65535)

    redis_host: str = "localhost"
    redis_port: int = Field(default=6379, gt=0, le=65535)

    rootmem_default_namespace: str = "default"
    rootmem_log_level: str = "INFO"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"


@lru_cache
def get_settings() -> Settings:
    """Load and validate settings once per process.

    Raises pydantic.ValidationError immediately if a value is invalid —
    callers should let this propagate at startup, not catch it.
    """
    return Settings()
