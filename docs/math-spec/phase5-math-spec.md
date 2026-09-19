# Phase 5 Math Spec

**N/A, with justification.** Phase 5 adds transport, identity and authorization; no scoring, ranking or estimation logic is introduced or changed. The only numeric facts are security parameters: tokens carry 256 bits of randomness (`secrets.token_urlsafe(32)`), stored as a SHA-256 digest. A 256-bit random token is not guessable and needs no key-stretching; a slow password hash would only add latency to every request.
