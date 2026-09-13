from __future__ import annotations

import pytest
from pydantic import ValidationError

from rootmem.config import Settings


def test_defaults_load_without_env_file() -> None:
    settings = Settings(_env_file=None)

    assert settings.postgres_port == 5432
    assert settings.redis_port == 6379
    assert settings.rootmem_default_namespace == "default"


def test_postgres_dsn_is_well_formed() -> None:
    settings = Settings(_env_file=None, postgres_host="db", postgres_port=5433)

    assert settings.postgres_dsn == (
        f"postgresql://{settings.postgres_user}:{settings.postgres_password}@db:5433/{settings.postgres_db}"
    )


def test_invalid_port_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, postgres_port=70000)
