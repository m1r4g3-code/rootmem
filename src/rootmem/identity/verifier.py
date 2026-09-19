"""Bearer-token verification for the HTTP transport (ADR 0027/0028).

Implements the SDK's `TokenVerifier` protocol. The identity's id and
namespaces travel in the returned `AccessToken.claims`, so tool handlers can
authorize without another database round trip. The lookup runs on every
request, so revoking an identity takes effect on its very next call.
"""

from __future__ import annotations

from mcp.server.auth.provider import AccessToken

from rootmem.identity.tokens import hash_token
from rootmem.storage.identity_protocols import IdentityRepository


class RootmemTokenVerifier:
    def __init__(self, identities: IdentityRepository) -> None:
        self._identities = identities

    async def verify_token(self, token: str) -> AccessToken | None:
        identity = await self._identities.get_by_token_hash(hash_token(token))
        if identity is None:
            return None
        return AccessToken(
            token=token,
            client_id=identity.name,
            scopes=[],
            subject=identity.id,
            claims={"identity_id": identity.id, "namespaces": list(identity.namespaces)},
        )
