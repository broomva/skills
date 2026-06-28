# Rate-limit discipline

The single hardest constraint on the Health skill. Get it wrong and Garmin **locks your account for 48–72 hours**. This document is the policy that prevents that.

## TL;DR

| Rule | Rationale |
|---|---|
| **15-minute minimum poll interval** for Garmin (per-source default) | `python-garminconnect` maintainer guidance; supported by issue-tracker history |
| **First 429**: exponential backoff (1m, 2m, 4m, 8m), max 4 retries within window | Standard transient-rate-limit recovery |
| **Second 429 within 10 minutes**: **HARD HALT** — no auto-retry | Triggers account-scoped lockout; only human can clear |
| **Never bypass the limiter** in code or by running multiple processes | Process-local limiter is per-process; concurrent sync processes are the most common foot-gun |
| **Backfills run as background jobs** that respect the 15-min floor | A year-scale API backfill takes ~10–12 hours by design |
| **Use the GDPR-export tarball** for cold-start, not API backfill | Zero rate cost; minutes instead of hours |

---

## Per-source policy table

| Source | Min poll interval | Per-day budget | Hard-halt trigger | Source of truth |
|---|---|---|---|---|
| **Garmin** | **15 min** | unspecified (account-scoped) | 2nd 429 within 10 min → 48–72h account lockout | `python-garminconnect` maintainer guidance; issue tracker |
| **Strava** | n/a (per-request) | **200/15min, 2000/day** | repeated 429 over hours triggers app-level throttle | https://developers.strava.com/docs/rate-limits/ |
| **Whoop** | per-endpoint documented | per-endpoint documented | repeated 429 → OAuth token revoked | https://developer.whoop.com/api/#section/Rate-Limiting |
| **Oura** | 5000/day | 5000/day | rare; documented well | https://cloud.ouraring.com/v2/docs |
| **Apple Health** | n/a (local) | n/a | n/a | local; no rate limit |
| **CGM (Dexcom)** | per-vendor | per-vendor | per-vendor | varies |

Strava is the canonical middle-tier comparison: their policy is publicly documented (200 requests / 15 minutes, 2000 / day). Garmin's policy is **not** publicly documented — what we know comes from `python-garminconnect`'s maintainer and the observed lockout patterns.

---

## The 429 cascade (Garmin)

Documented in `cyberjunky/python-garminconnect` issues and (historically) on `matin/garth`. The empirical pattern:

### Stage 1 — first 429 (per-request rate limit)

What it looks like: an HTTP 429 with a `Retry-After` header (usually 30–120 seconds). The rest of the account is unaffected; other endpoints still work.

What to do: back off exponentially. The default policy:
- Wait `min(retry_after_s + 60s, 60s)` jitter then retry.
- Doublings: 1m → 2m → 4m → 8m, max 4 retries.
- After all retries fail, surface `RateLimited` to the caller with `retry_after_s` populated.

Recoverable.

### Stage 2 — second 429 within 10 minutes (account-scoped lockout)

What it looks like: every endpoint returns 429 for **48 to 72 hours**. The `Retry-After` header (when present) lies — even after waiting it out, the next call returns 429 again until the lockout clears.

What to do: **hard halt**. Do not auto-retry. The agent surfaces the issue to the user and stops all sync activity for the affected source.

Recovery: wait 48–72h. There is no shortcut. Some users have reported that contacting Garmin support shortens the lockout, but support is not on the engineering team's path and the response time is days.

Documented evidence:
- https://github.com/cyberjunky/python-garminconnect/issues — search "429" / "rate limit" / "locked"
- (Historical) https://github.com/matin/garth/issues — pre-deprecation issues

### Stage 3 — repeated lockouts across days

What it looks like: the lockout pattern repeats every time you try to sync, including after a multi-day cooldown.

What to do: assume the account is flagged for review. **Do not run any sync.** Log into Garmin Connect in a browser; check for security challenges; consider re-running `health auth login` to refresh the cookie cleanly; in the worst case, contact Garmin support.

This is **not** common. It's the failure mode of running an over-eager backfill against the API instead of via the GDPR tarball.

---

## Implementation — the `RateLimiter` port

```python
@runtime_checkable
class RateLimiter(Protocol):
    def acquire(self, key: str) -> None: ...
    def record_success(self, key: str) -> None: ...
    def record_429(self, key: str, retry_after_s: float | None = None) -> None: ...
```

The default adapter, `TokenBucketRateLimiter`, implements:
- `acquire(key)` — blocks until a slot is available. Per-key minimum interval (default 15 min for Garmin keys).
- `record_success(key)` — resets the backoff counter for the key.
- `record_429(key, retry_after_s=...)` — bumps backoff. The second `record_429` within 10 minutes raises `RateLimited` on the next `acquire`, preventing the lockout.

All use cases (`SyncSourceUseCase`, `BackfillSourceUseCase`) acquire the limiter slot **before** any source operation. Adapters also acquire (per-endpoint) before each network call. Double-acquire is intentional — the use-case slot rate-limits the *whole operation*, the per-endpoint slot rate-limits the *individual call*.

---

## What "never bypass" means

Common bypass patterns to **never** ship:

1. **Running two sync processes in parallel** — the rate-limiter is in-process; two processes are two independent buckets and Garmin sees both. Single-source sync is single-process.
2. **`time.sleep(60)` instead of acquiring the limiter** — the limiter knows the *real* state (last call, last 429); a hard-coded sleep doesn't.
3. **Catching `RateLimited` and retrying immediately** — the limiter raised `RateLimited` for a reason. Re-raise; let the agent or the user decide.
4. **Lowering the 15-min floor "just for backfill"** — the floor is for backfill too. Use the GDPR tarball if you need to go faster.
5. **Running sync from a cron that fires every minute** — the limiter will refuse most calls, but each refusal still counts toward Garmin's anti-abuse heuristics. Cron at the actual sync interval (15+ min).

Each of these is a P20 (Cross-Review) blocker.

---

## Persist (P12) discipline for long-running backfills

A year-scale backfill via the API takes ~10–12 hours respecting the 15-min floor. This is too long for a single agent session.

Use Persist:

```bash
persist iterate skills/Health/backfill.md
```

Where `backfill.md` is a PROMPT with `--strategy api-incremental --chunk-days 7`. Each iteration:
- syncs one week
- sleeps until the rate-limiter clears (or exits cleanly)
- updates `state.jsonl` with the last-completed week

The next iteration spawns a fresh context, reads `state.jsonl`, resumes. Long-horizon work without context decay — per the P12 invariant in CLAUDE.md.

---

## Telemetry

The limiter does **not** phone home. Limiter state is local. The `rate_limit_remaining_s` field on `SyncResult` is informational and read from the in-process limiter — no external service queried.

---

## References

- `python-garminconnect`: https://github.com/cyberjunky/python-garminconnect
- (deprecated) `garth`: https://github.com/matin/garth
- Strava rate limits: https://developers.strava.com/docs/rate-limits/
- Whoop rate limits: https://developer.whoop.com/api/#section/Rate-Limiting
- Oura API docs: https://cloud.ouraring.com/v2/docs
- [garmin-api-landscape-2026.md](garmin-api-landscape-2026.md) — full substrate landscape
- [privacy-architecture.md](privacy-architecture.md) — token + DB security
