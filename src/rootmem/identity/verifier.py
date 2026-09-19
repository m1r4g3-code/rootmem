"""Bearer-token verification for the HTTP transport (ADR 0027/0028/0033).

Implements the SDK's `TokenVerifier` protocol. The identity's id, namespaces
and scope travel in the returned `AccessToken.claims`, so tool handlers can
authorize without another database round trip. The lookup runs on every
request, so revoking, rotating or expiring an identity takes effect on its
very next call.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from mcp.server.auth.provider import AccessToken

from rootmem.identity.tokens import hash_token
from rootmem.storage.identity_protocols import IdentityRepository


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RootmemTokenVerifier:
    def __init__(
        self, identities: IdentityRepository, clock: Callable[[], datetime] = _utc_now
    ) -> None:
        self._identities = identities
        self._clock = clock

    async def verify_token(self, token: str) -> AccessToken | None:
        identity = await self._identities.get_by_token_hash(hash_token(token))
        if identity is None or identity.is_expired(self._clock()):
            return None
        return AccessToken(
            token=token,
            client_id=identity.name,
            scopes=[],
            subject=identity.id,
            expires_at=int(identity.expires_at.timestamp()) if identity.expires_at else None,
            claims={
                "identity_id": identity.id,
                "namespaces": list(identity.namespaces),
                "scope": identity.scope,
            },
        )
