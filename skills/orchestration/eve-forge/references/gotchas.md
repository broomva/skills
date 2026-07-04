# eve gotchas (distilled from the driven benchmark, BRO-1677)

Every item here bit a real run. The `eve-forge` gates exist because of these.

1. **Node-24 hard requirement (the npx trap).** `npx eve@latest init` silently
   resolves the *system* Node; if that's < 24 it **hard-fails**. Even with Node 24
   installed via nvm, `npx` may pick the wrong one. → Always `python3 scripts/eve_forge.py
   preflight` then `nvm use 24` before scaffolding.

2. **Non-TTY `eve dev`.** `eve init` auto-launches `eve dev --input /model`, which errors
   in a non-TTY / headless / agent context (`--input requires the interactive UI`). The
   scaffold itself succeeds; only the auto-dev-launch fails. Ignore the noise; don't treat
   it as a scaffold failure.

3. **Fail-closed default auth (a good default, but not prod-ready as shipped).** The scaffold
   channel ships `auth: [vercelOidc(), localDev(), placeholderAuth()]`, which rejects
   anonymous production traffic. `placeholderAuth()` is a scaffold stub — replace with a real
   authenticator. **NEVER ship `none()` in prod** — a benchmark run did, leaving a public,
   Gateway-billed endpoint anyone could drain. The `deploy-safety` gate blocks this.

4. **Vercel Deployment Protection (SSO).** The raw deployment URL 302-redirects to
   `vercel.com/sso-api` (platform-level, in front of eve's always-public `/health`). The
   **production alias** (`<slug>.vercel.app`) is public. → Use the alias for smoke-tests and
   the customer-facing URL, not the raw deployment URL.

5. **eve not auto-detected as a Vercel framework.** Deploy logs "No framework detected"; it
   works only because the scaffold's `build` script is `eve build`. Consequence: eve's native
   **Agent-Runs observability likely does NOT activate** for the team — rely on the stream API
   (`GET /eve/v1/session/:id/stream`) for observability, not the dashboard tab.

6. **AI-Gateway auth is automatic on Vercel.** Deployed eve agents authenticate models via
   **project OIDC** at runtime — **zero keys** to configure. (Local/VPS runs need a key.)
   Gateway credits are finite — keep live runs minimal during forging + smoke.

7. **Stream long-poll obscures latency.** The NDJSON stream holds open at `session.waiting`
   until the socket cap — so `curl time_total` ≠ turn latency. Diff event `meta.at` timestamps
   for real per-turn latency.

8. **Pin versions.** eve is beta (v0.19.x at benchmark time); its CLI + file conventions move.
   Pin the eve + `claude` CLI versions and re-validate the templates when bumping.
