I’ll keep this planning-only: no code, tests, deployment, or merge changes.

Plan:

1. Map the existing reset lifecycle: issuance, storage/signing, validation, password update, and session invalidation.
2. Define one-time-use semantics: expiry, rotation/invalidation of older tokens, and consistent invalid-token responses.
3. Refactor redemption to an atomic server-side consume operation—validate token, mark it consumed, and update the password in one transaction/conditional write so concurrent requests cannot both succeed.
4. Store only token digests (or persist a `jti` for signed tokens), with `issued_at`, `expires_at`, and `consumed_at`/revocation state.
5. Add tests for successful first use, replay rejection, concurrent redemption, expiration, token rotation, malformed tokens, and session revocation after reset.
6. Run the project’s check/test harness and report the resulting diff and any migration or compatibility considerations.