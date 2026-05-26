# Garmin API landscape — May 2026

## TL;DR

Garmin Connect has **no official personal-tier API**. The 2026 client landscape is:

| Substrate | Status May 2026 | Verdict for personal KG |
|---|---|---|
| **garth** | Deprecated 2026-03-28 (mobile-SSO killed by Cloudflare WAF) | Do NOT use |
| **python-garminconnect ≥ 0.3.4** | Active (widget+cffi bypass; 2.3k★) | **Adopt** (v1 default) |
| **eddmann/garmin-connect-cli v1.0.1** | Reference shape only | Mimic command surface; do NOT wrap |
| **Garmin Health API (enterprise)** | Live, no personal tier | Not viable — corporate accounts only |
| **Strava** | Live, OAuth | Not viable — no sleep / HRV / Body Battery |
| **Wahoo / Polar / Suunto APIs** | Limited / gated | Not viable for KG depth |
| **GDPR "Export Your Data" tarball** | Live (queue, hours-to-days) | **Use** for cold-start backfill |

The combination chosen for `broomva-health` v1: **python-garminconnect for live ingest + GDPR-tarball for historical cold-start.**

This document records *why*. Future maintainers should read this before swapping the substrate — the deprecations and rate-limit history matter.

---

## 1. garth — deprecated

`garth` (https://github.com/matin/garth) was the previously-recommended Python client for Garmin Connect. It used the mobile SSO login flow (the same flow Garmin's iOS / Android app uses) which gave it a clean OAuth-token surface and decent staying power against UI-level WAF changes.

**What happened:** On **2026-03-28**, Garmin tightened Cloudflare WAF rules on the mobile-SSO endpoint. `garth` could no longer pass the bot challenge. The maintainer announced deprecation on the repo's README and stopped releasing fixes. As of May 2026 the package still installs but every `login()` call fails with a 403.

References:
- https://github.com/matin/garth — README banner ("DEPRECATED 2026-03-28")
- Issue tracker: bot-challenge failures begin around 2026-03-26, all attempts to circumvent rejected by Garmin
- Migration guidance from upstream: switch to `python-garminconnect` ≥ 0.3.4

**Implication for us:** Anything in this codebase referencing `garth` is a vestige. The optional `garth.*` ignore in `pyproject.toml`'s mypy overrides exists only to tolerate transitive imports through `python-garminconnect`'s `_compat` shims; we never `import garth` directly.

---

## 2. python-garminconnect — adopted

`python-garminconnect` (https://github.com/cyberjunky/python-garminconnect) is a long-running community client. Maintainer `cyberjunky` has shipped active updates throughout 2026, including the **0.3.x widget+cffi bypass** that replaced the mobile-SSO path after garth's deprecation.

Why this one:
- **Active maintenance** — 0.3.4 released after the March 2026 WAF change; the issue tracker is responsive (24–48h triage on auth-class issues).
- **Coverage** — sleep, HRV (overnight & nap), Body Battery, Training Readiness, Training Status, Stress, VO2max, Fitness Age, daily summary, weight, body composition, activity list with FIT export, hydration. Effectively everything in `MetricCode` that Garmin records.
- **MFA-friendly** — the 0.3.x line supports interactive MFA prompts; integrates cleanly with our `MFAProvider` port (env / prompt / Keychain).
- **2.3k stars** as of May 2026 — wide use means breakage is detected fast.

Why not wrap a higher-level library:
- Higher-level layers (`fitnotes`, `garmin-sync`, etc.) tend to add their own schema, opinion about reconciliation, and storage. We deliberately keep our own domain shape (HKSample-derived). The adapter calls `garminconnect.Garmin(...).get_*()` and constructs our `QuantitySample` / `Workout` directly.

Pinning policy: `python-garminconnect>=0.3.4`. We do **not** pin a maximum because the API surface has been stable through the 0.3.x line and the maintainer's release notes are explicit about breaking changes.

References:
- https://github.com/cyberjunky/python-garminconnect
- https://pypi.org/project/garminconnect/
- 0.3.4 changelog: widget-based auth bypass for Cloudflare WAF (Apr 2026)

---

## 3. eddmann/garmin-connect-cli v1.0.1 — command-shape reference

https://github.com/eddmann/garmin-connect-cli (v1.0.1, MIT, Apr 2026) is a Node CLI over the Garmin Connect API. It's well-designed: clean subcommands, deterministic exit codes (0/1/2 with `2` reserved for auth-required), `--format json|csv|table` flag uniform across commands.

**We do NOT wrap or shell out to it.** We use it as a **reference for command surface** — our Typer CLI mirrors the subcommand names and exit-code conventions so users coming from `eddmann/garmin-connect-cli` find the muscle memory transfers. Specifically:

- `auth login` / `auth status` / `auth logout` — matches eddmann
- Exit `2` for auth-required — matches eddmann
- `--format json|jsonl|csv|tsv|human` — we add `jsonl` + `tsv` + `human`; the rest matches

We own the Python interface because (a) we want pydantic v2 typing throughout, (b) we want the synthesis layer in the same process as the trace store, (c) Node→Python interop adds latency and a deploy dep we don't need.

URL: https://github.com/eddmann/garmin-connect-cli

---

## 4. Garmin Health API (enterprise) — not viable

https://developer.garmin.com/gc-developer-program/health-api/

The Garmin Health API is the **only Garmin-blessed API surface** but it is **enterprise-only**: requires a partnership agreement, an OAuth 1.0a integration, an approval process, and a contract. Costs are not public; programs require commercial use cases.

Why not viable for personal KG:
- Cannot get an account as an individual.
- The endpoints serve aggregated daily summaries — far less granular than what `python-garminconnect` exposes from the consumer Connect site.
- Long-term: a future B2B variant of the Broomva stack might use this; for personal use, it's a non-starter.

---

## 5. Strava — middle-tier substrate, not viable for health KG

https://developers.strava.com/

Strava has a clean OAuth API with rate limits documented (200 requests / 15 minutes, 2,000 / day per app — see https://developers.strava.com/docs/rate-limits/).

Why not viable as our substrate:
- **No sleep, no HRV, no Body Battery, no resting HR, no overnight metrics.** Strava is an activity platform; the metrics that matter for a health KG (HRV-CV, sleep architecture, RHR trend) simply do not exist on the platform.
- We *can* use Strava as a **complementary** workout source — eventually, an adapter under `adapters/sources/strava.py` could pull power-meter-based workouts when Garmin's TSS is unavailable. Not in v1.

---

## 6. Wahoo / Polar / Suunto APIs

- **Wahoo** — no public personal-tier API. Some reverse-engineered Python clients exist; none with the activity coverage to justify an adapter.
- **Polar** — has an "Accesslink API" (https://www.polar.com/accesslink-api/) but it gates sleep/HRV behind partnership.
- **Suunto** — has the Suunto App API but it's read-only-from-app, not sync-friendly.

None of these compete with Garmin for personal KG depth. If a user is on one of these ecosystems primarily, the **Apple Health** path (when the v2 adapter ships) is the better merge point — Apple Health aggregates from all of them on iOS.

---

## 7. GDPR "Export Your Data" tarball — cold-start path

Under EU GDPR Article 20 (right to data portability), Garmin must provide a full account export on request. UI path: **Garmin Connect → Settings → Account Information → "Export Your Data"**.

What you get:
- A `.zip` containing per-day JSON summaries, raw `.fit` files for every activity, sleep / HRV / wellness folders.
- Generation is queued; delivery time is hours to days (Garmin's queue, not our control).
- Zero API rate-limit cost — the tarball is generated server-side from Garmin's own warehouse.

How we use it:
- The Backfill workflow's `--strategy gdpr-tarball` flag (see [../Workflows/Backfill.md](../Workflows/Backfill.md)) unpacks the tarball, walks the per-day files, and writes the trace DB in batches.
- This is **the** correct cold-start path. Doing a year-scale backfill via the API is possible (~10–12 hours respecting the 15-min floor) but the tarball does the same thing in minutes and costs zero rate budget.

---

## 8. Rate-limit history

This is the section every future maintainer must read before "optimizing" the rate-limiter.

### The 15-minute poll floor

`python-garminconnect`'s maintainer (`cyberjunky`) has stated on the issue tracker that **the safe minimum poll interval for personal accounts is 15 minutes**. Going below is what triggers the patterns below.

### The 429 cascade

Observed behavior, documented across multiple issues on `cyberjunky/python-garminconnect` and `matin/garth` (before garth's deprecation):

1. **First 429** within a polling window: per-request rate limit. Back off exponentially; the next call after `retry_after_s` typically succeeds.
2. **Second 429 within ~10 minutes:** account-scoped rate limit kicks in. The endpoint returns 429 for **48–72 hours** on every call. No retry strategy recovers; you wait it out.
3. **Pattern of repeated 429s over days:** account flagged. Re-login required, MFA challenged, and in rare cases the account is temporarily suspended (requires manual contact with Garmin support).

This is not theoretical — the issue tracker has multiple posts with users locked out for 48–72h after running over-eager backfill scripts.

Our limiter encodes this into the `record_429` semantics: after the first 429 we back off exponentially; the **second** 429 within 10 minutes triggers a hard halt that's only cleared by the human.

See [rate-limit-discipline.md](rate-limit-discipline.md) for the full policy.

---

## 9. Open watchlist (revisit quarterly)

| Substrate | Watch for | Trigger to re-evaluate |
|---|---|---|
| garth | If Garmin reopens mobile-SSO | Maintainer announces undeprecation |
| python-garminconnect | API surface stability through 0.4.x / 1.0 | Major version bump or new auth flow |
| Garmin Health API | If a personal tier appears | Garmin developer-program newsletter |
| Apple Health | macOS HealthKit-on-Mac if Apple ever ships it | WWDC announcements |
| Whoop | OAuth API surface expansion | https://developer.whoop.com/api |
| Oura | API v2 evolutions | https://cloud.ouraring.com/v2/docs |

Cadence: quarterly P15 reflex. Update this table in place.

---

## All cited URLs

- https://github.com/matin/garth
- https://github.com/cyberjunky/python-garminconnect
- https://pypi.org/project/garminconnect/
- https://github.com/eddmann/garmin-connect-cli
- https://developer.garmin.com/gc-developer-program/health-api/
- https://developers.strava.com/
- https://developers.strava.com/docs/rate-limits/
- https://www.polar.com/accesslink-api/
- https://developer.whoop.com/api
- https://cloud.ouraring.com/v2/docs
