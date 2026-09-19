"""Bearer token generation and hashing (ADR 0027).

Tokens are 256 bits of randomness, shown once and stored only as a SHA-256
digest. A fast hash is correct here: the secret is uniformly random, so there
is nothing to brute-force or stretch (docs/math-spec/phase5-math-spec.md).
"""

from __future__ import annotations

import hashlib
import secrets

TOKEN_PREFIX = "rmk_"


def generate_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
