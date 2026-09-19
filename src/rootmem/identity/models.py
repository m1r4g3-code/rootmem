"""Agent identity (ADR 0027). Pure data, no I/O."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

# Only the trusted local (stdio) identity owns every namespace; issued
# identities may not be created with it (see identity.cli).
ALL_NAMESPACES = "*"


class Identity(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    namespaces: list[str]
    created_at: datetime
    revoked_at: datetime | None = None

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None


def local_identity(name: str, created_at: datetime) -> Identity:
    """The fixed, trusted identity used for stdio, where the caller is the
    local process that launched the server (no behavior change, ADR 0029)."""
    return Identity(id="local", name=name, namespaces=[ALL_NAMESPACES], created_at=created_at)
