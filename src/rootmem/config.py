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

    # Phase 2 Bayesian belief update (ADR 0013), replacing ADR 0008's flat
    # confidence-floor rule — see docs/math-spec/phase2-math-spec.md for the
    # full derivation. All provisional defaults, not calibrated against real
    # retrieval-outcome data yet (docs/research/phase2-research-memo.md).
    bayesian_prior_strength: float = Field(default=2.0, gt=0.0)
    bayesian_supersede_margin: float = Field(default=0.05, ge=0.0, le=1.0)
    bayesian_source_reliability_extracted: float = Field(default=0.7, ge=0.0, le=1.0)
    bayesian_source_reliability_distilled: float = Field(default=0.85, ge=0.0, le=1.0)
    bayesian_source_reliability_feedback: float = Field(default=1.0, ge=0.0, le=1.0)

    # Phase 2 consolidation trigger (ADR 0012/docs/math-spec/phase2-math-spec.md).
    consolidation_episode_threshold: int = Field(default=500, gt=0)
    consolidation_time_window_hours: float = Field(default=24.0, gt=0.0)
    consolidation_batch_size: int = Field(default=500, gt=0)

    # Phase 2 distillation clustering (ADR 0015) — 0.80 validated empirically
    # by scripts/spike_similarity_clustering.py against real voyage-4
    # embeddings, not asserted from first principles.
    distillation_similarity_threshold: float = Field(default=0.80, ge=0.0, le=1.0)
    distillation_min_cluster_size: int = Field(default=2, ge=2)
    # Defaults to extraction_model's value at settings-construction time if
    # left unset (see the property below) — distillation reuses the same
    # Haiku-tier model unless a future phase has reason to diverge.
    distillation_model: str | None = None

    # Phase 2 salience scoring (ADR 0016/docs/math-spec/phase2-math-spec.md).
    # task_relevance's weight is 0.0: no task-modeling primitive exists yet
    # to compute it from (honestly zeroed, not silently omitted from the
    # formula's shape).
    salience_weight_novelty: float = Field(default=1 / 3, ge=0.0)
    salience_weight_importance: float = Field(default=1 / 3, ge=0.0)
    salience_weight_repetition: float = Field(default=1 / 3, ge=0.0)
    salience_weight_task_relevance: float = Field(default=0.0, ge=0.0)
    repetition_similarity_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    novelty_neighbor_sample_size: int = Field(default=10, gt=0)
    salience_repetition_saturation_count: int = Field(default=3, gt=0)

    @property
    def distillation_model_or_default(self) -> str:
        return self.distillation_model or self.extraction_model

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
