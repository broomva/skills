I’ll prepare a review-ready, local-only refactor plan to make password-reset tokens single-use; no code, tests, deployment, or merge will occur in this planning exercise.

- **Intent:** A reset token may succeed exactly once; subsequent or concurrent replay attempts are rejected.
- **Bounds:** May inspect and change application code/tests locally in a future execution. No deploy, merge, external communication, or credential changes. Default approach: minimal durable token-consumption state with an atomic consume-and-reset operation.
- **Evidence:** Tests prove valid first use succeeds; reused, expired, malformed, and concurrent duplicate uses fail; existing reset behavior remains intact. Run `make check` before `make test`.
- **Escalation:** I’ll pause if the flow is fully stateless and preventing replay requires a new persistence/security-model decision, or if token invalidation semantics conflict with another recovery flow.
- **Review:** An independent code review/session verifies the atomicity and test coverage before the work is called complete.

Plan:

1. Map the reset-token lifecycle: issuance, storage/encoding, validation, password update, and existing tests.
2. Choose the smallest compatible single-use mechanism—prefer an atomic database update/transaction that validates an active token, updates the password, and consumes or removes the token in one operation.
3. Ensure a failed password update does not accidentally consume a token, and concurrent requests cannot both succeed.
4. Add focused regression tests for first use, replay, expiry, invalid token, and racing duplicate submissions.
5. Run static checks and the full test suite; exercise the affected route/service behavior directly.
6. Obtain independent review of the persistence/query semantics and test adequacy.
7. Record the chosen token lifecycle and concurrency guarantee in the project’s decision context.

Actions taken in this exercise: reversible planning only. No code was changed and no checks were run.