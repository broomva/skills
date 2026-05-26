# tradingview-bridge

Webhook receiver + multi-broker executor for TradingView Pine Script alerts. Dispatches by `asset_class` to IBKR (stocks/bonds/FX), Kraken (crypto), and Polymarket (prediction markets) — paper-only, mock-by-default for CI.

**Status: PR 2 (v0.2.0) — receiver + executor + idempotency + rate limit + bookkeeping. Paper-only enforced at startup. Real-paper broker SDKs are an optional extras group (`tradingview-bridge[brokers]`).**

- Workspace ticket: [`broomva/workspace tasks/bro-167`](https://github.com/broomva/workspace/blob/main/tasks/bro-167-cross-asset-trading-platform.md)
- Canonical decision record (broker selection): [`broomva/workspace docs/specs/2026-05-22-broker-selection-cross-asset.html`](https://github.com/broomva/workspace/blob/main/docs/specs/2026-05-22-broker-selection-cross-asset.html)

## Architecture (PR 2 ships everything below + skeletons for real-paper)

```
TradingView Pine Script alert
        │  POST /webhook  (shared-secret in body, TV source IP)
        ▼
  ┌──────────────────────────────┐
  │  FastAPI app                 │
  │  ├ verify source IP          │   (PR 1)
  │  ├ rate limit (token bucket) │   (PR 2)
  │  ├ parse + validate TVAlert  │   (PR 1)
  │  ├ constant-time secret cmp  │   (PR 1)
  │  └ dispatcher.dispatch()     │
  └──────────────┬───────────────┘
                 ▼
  ┌──────────────────────────────┐
  │  Dispatcher                  │
  │  ├ asset_class → broker      │   (PR 1, pure function)
  │  ├ idempotency check         │   (PR 2, SQLite)
  │  ├ broker client.place_order │   (PR 2)
  │  └ schedule_journal()        │   (PR 2, fire-and-forget)
  └──────────────┬───────────────┘
                 ▼
  ┌──────────────────────────────┐
  │  BrokerClient ABC            │   (PR 2)
  │  ├ MockClient   (default)    │   ← what tests + CI use
  │  ├ IBKRClient   (real-paper) │   ← skeleton; PR 2b wires ib_async
  │  ├ KrakenClient (real-paper) │   ← skeleton; PR 2b wires ccxt sandbox
  │  └ PolymarketClient          │   ← skeleton; PR 2b wires py-clob-client
  └──────────────────────────────┘
                 │
                 ▼  (PR 3, fire-and-forget)
        Bookkeeping CLI subprocess
        → research/entities/pattern/strategy-{name}.md
```

## What's in PR 2

**Broker layer (`src/tradingview_bridge/clients/`):**
- `base.py` — `BrokerClient` ABC + `OrderReceipt` + `NotConfiguredError`
- `mock.py` — `MockClient` (in-memory, used by every test)
- `ibkr.py`, `kraken.py`, `polymarket.py` — real-paper skeletons; in mock mode they delegate to `MockClient`. Real-paper mode raises `NotConfiguredError` until PR 2b wires the SDKs.

**Infrastructure:**
- `idempotency.py` — `IdempotencyStore` (aiosqlite), keyed on `alert_id`. Duplicate alerts get `status="duplicate"` + same `order_id`.
- `ratelimit.py` — `TokenBucketLimiter` (per-IP, 60-second sliding window). 429 on exceedance.
- `bookkeeping.py` — `schedule_journal()` fires a subprocess to the workspace bookkeeping CLI. Graceful no-op when CLI not on PATH.

**Dispatcher updates (`dispatch.py`):**
- Constructor: `Dispatcher(broker_mode, idempotency_store, clients_override)`
- `dispatch(alert)` now: route → idempotency peek → client.place_order → store insert → journal → return `accepted`/`duplicate`/`rejected`.
- Health check aggregates per-broker connectivity.

**Tests (44+ cases across 7 files):**
- `test_idempotency.py`, `test_ratelimit.py`, `test_clients_mock.py`, `test_clients_interface.py` — new
- `test_dispatch.py`, `test_webhook_smoke.py` — updated to assert `accepted` / `duplicate` / 429
- All run in `TVBRIDGE_BROKER_MODE=mock` — no broker creds needed in CI.

**Schema changes (`schemas.py`):**
- `DispatchResult.status` now `accepted | rejected | stubbed | duplicate`
- `DispatchResult.order_id: str | None` — broker order id (None for stubbed/rejected)

**Policy (`.control/policy.yaml`):**
- 6 deferred PR 1 gates promoted to active: `webhook-rate-limit`, `alert-idempotency`, `broker-mode-mock-default`, `real-paper-requires-creds`, etc.
- 4 new gates deferred to PR 3+ — per-broker position cap, Formulario 4 reminder, CFD broker block, journal-required.

## What's deliberately NOT in PR 2 (deferred to PR 2b or later)

- Real `ib_async` / `ccxt` / `py-clob-client` wiring (skeletons exist; PR 2b after broker onboarding)
- Per-broker position cap reader (needs real broker positions API — PR 3)
- Formulario 4 reminder gate (needs capital-transfer detection — PR 3)
- Pine Script alpha library + Interceptor chart screencap (PR 3)
- Trading-bot cookbook entry + Evals trading domain (PR 4)

## Local dev

```bash
cd services/tradingview-bridge

uv sync --extra dev
# To experiment with real-paper SDKs (not tested in CI):
# uv sync --extra dev --extra brokers

cp .env.example .env  # then edit TVBRIDGE_TV_WEBHOOK_SECRET

uv run pytest -v
uv run ruff check . && uv run ruff format --check . && uv run mypy src

# Run the service in mock mode (default)
TVBRIDGE_TRADING_MODE=paper TVBRIDGE_TV_WEBHOOK_SECRET=$(cat .env | grep SECRET= | cut -d= -f2) \
  uv run uvicorn tradingview_bridge.app:app --reload --port 8787

# Smoke test (in another terminal)
curl -X POST http://127.0.0.1:8787/webhook \
  -H 'Content-Type: application/json' \
  -H 'X-Forwarded-For: 52.89.214.238' \
  -d '{"alert_id":"test-001","secret":"<your secret>","strategy_name":"smoke","asset_class":"stock","symbol":"AAPL","action":"buy","size":"10","size_type":"units","time":"2026-05-23T15:00:00Z"}'
```

Expected `200 OK` with body like `{"status":"accepted","broker":"ibkr","alert_id":"test-001","order_id":"mock-<uuid12>","detail":"Order placed by ibkr (paper=True)."}`.

Re-fire the same alert_id → `{"status":"duplicate","broker":"ibkr","alert_id":"test-001","order_id":"<same mock id>",...}`.

## TradingView Pine Script alert template

```pinescript
// In Pine Script v5 alert message body:
{
  "alert_id": "{{strategy.order.id}}",
  "secret": "REPLACE_WITH_YOUR_TVBRIDGE_TV_WEBHOOK_SECRET",
  "strategy_name": "momentum-spy-15m",
  "asset_class": "stock",
  "symbol": "{{ticker}}",
  "action": "{{strategy.order.action}}",
  "size": "{{strategy.position_size}}",
  "size_type": "units",
  "price_hint": "{{close}}",
  "time": "{{time}}"
}
```

Webhook URL in the alert dialog: `https://your-host/webhook`. HTTPS required by TradingView; use Cloudflare Tunnel or ngrok for local dev.

## Switching to real-paper mode (PR 2b)

```bash
# 1. Install broker SDKs
uv sync --extra dev --extra brokers

# 2. Set broker credentials (see .env.example)
export TVBRIDGE_BROKER_MODE=real-paper
export TVBRIDGE_IBKR_HOST=127.0.0.1
export TVBRIDGE_IBKR_PORT=7497         # TWS paper port
# (and similarly TVBRIDGE_KRAKEN_*, TVBRIDGE_POLYMARKET_*)

# 3. Start TWS in paper mode (manual step — TWS doesn't headless)

# 4. Re-run the service
uv run uvicorn tradingview_bridge.app:app --port 8787
```

PR 2 ships the skeletons that raise `NotConfiguredError` when env vars are missing. PR 2b replaces the skeleton bodies with real SDK calls.

## Safety

- **PAPER_ONLY** enforced at startup — `TVBRIDGE_TRADING_MODE` must be `paper`; otherwise the lifespan hook exits 1.
- **Mock-default broker mode** — no broker contact unless operator explicitly sets `TVBRIDGE_BROKER_MODE=real-paper` AND provides credentials.
- **Idempotency** prevents double-fire on Pine Script retries (same `alert_id` → same `order_id`).
- **Rate limiting** prevents runaway strategies (default 60 req/min per source IP).
- **Constant-time secret comparison** — `hmac.compare_digest` against `TVBRIDGE_TV_WEBHOOK_SECRET`.
- **TradingView IP allowlist** — defense-in-depth alongside the shared secret.
- **Bookkeeping journal** — every accepted alert lands in `research/entities/pattern/strategy-{name}.md` via the workspace bookkeeping CLI (graceful no-op if CLI not reachable).

## See also

- `SKILL.md` (this repo) — parent skill
- [`broomva/finance-substrate`](https://github.com/broomva/finance-substrate) — tax substrate (Form 210, DIAN, TRM)
- [Broker selection ADR](https://github.com/broomva/workspace/blob/main/docs/specs/2026-05-22-broker-selection-cross-asset.html)
- [Linear ticket BRO-167](https://github.com/broomva/workspace/blob/main/tasks/bro-167-cross-asset-trading-platform.md)
