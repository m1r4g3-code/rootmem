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
    # "prefer" (not "require"): negotiates SSL with hosts that offer it (e.g.
    # Neon, which mandates SSL) while still connecting to a local Postgres
    # that has no SSL configured at all (the Phase 0 native/Docker setups).
    postgres_sslmode: str = "prefer"

    redis_host: str = "localhost"
    redis_port: int = Field(default=6379, gt=0, le=65535)

    rootmem_default_namespace: str = "default"
    rootmem_log_level: str = "INFO"

    # Phase 1 external LLM APIs (ADR 0009). None by default — code paths
    # that need them (EmbeddingProvider/ExtractionProvider real
    # implementations) fail explicitly if unset, at the point of use, not
    # here — a fakes-only unit test run needs neither key.
    voyage_api_key: str | None = None
    anthropic_api_key: str | None = None

    # voyage-4 @ 1024 dims, HNSW (ADR 0007) — explicitly provisional, see
    # docs/research/phase1-research-memo.md's open questions.
    voyage_model: str = "voyage-4"
    voyage_output_dimension: int = 1024

    # Haiku-tier, per ADR 0009 — exact dated ID checked against actual
    # availability, not guessed (same discipline as ADR 0002).
    extraction_model: str = "claude-haiku-4-5-20251001"
    extraction_max_tokens_per_call: int = Field(default=4096, gt=0)

    # Provisional linear blend weights (ADR 0007/phase1-math-spec) — equal
    # weight by default, revisit once real usage data exists.
    hybrid_search_weight_text: float = Field(default=0.5, ge=0.0)
    hybrid_search_weight_vector: float = Field(default=0.5, ge=0.0)

    # ADR 0008's deterministic contradiction rule: most-recent-wins above
    # this floor, else both sides are flagged contested.
    contradiction_confidence_floor: float = Field(default=0.5, ge=0.0, le=1.0)

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            f"?sslmode={self.postgres_sslmode}"
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
