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

## TradingView Paper Trading mode (`tradingview-paper`)

The **fastest** path to a real executed (simulated) book under autonomous control — **zero KYC, zero capital, instant**. Instead of routing to an external broker, the bridge controls TradingView's **built-in Paper Trading simulator** directly.

TradingView has **no inbound trading API** (webhooks only go *out*), so control is via **browser automation of the Trading Panel** using the [Interceptor](https://github.com/Hacker-Valley-Media/slop-browser) CLI (real Chrome, your logged-in session, passes bot detection). The `TradingViewPaperClient` conforms to the same `BrokerClient` ABC as IBKR/Kraken — the dispatcher and the autonomous operator treat it identically.

```bash
# Prereqs (one-time): Interceptor extension installed + active in Chrome,
# logged into TradingView, Paper Trading connected in the Trading Panel.

export TVBRIDGE_TRADING_MODE=paper
export TVBRIDGE_TV_WEBHOOK_SECRET=$(openssl rand -hex 32)
export TVBRIDGE_BROKER_MODE=tradingview-paper   # ← all alerts → TradingView Paper

uv run uvicorn tradingview_bridge.app:app --port 8787
# every alert now drives your TradingView Paper account; the operator
# (`operate run`) manages it under the self-dogfood interlock.
```

**How it works** (selectors pinned from a live session):
- navigate the chart to the alert's `symbol` (`/chart/?symbol=…`)
- idempotently connect Paper Trading (Trade → Paper Trading) if not already
- click the side control (`Buy…`/`Sell…`), set quantity, confirm
- read positions / account balance / PnL from the panel

**Order-management surface** (full lifecycle):
- `place_order(buy/sell)` — market order via the ticket, with a **double-submit guard** (the ticket submit is only clicked if it is a distinct element from the quick button, so a quick button that places immediately never double-fires)
- `place_order(close)` → `close_position(symbol)` — close the position for that symbol
- `place_order(flatten)` → close **all** open positions
- `cancel_order(symbol)` — cancel a working order
- `list_positions()` — open positions keyed by `EXCHANGE:TICKER`
- `list_orders()` — *working* orders only (gated on the `Orders N` tab count, so the order-entry ticket button is never reported as a phantom working order)

Browser/Interceptor unreachable → `NotConfiguredError` → `rejected` (never touches the account on an unverified surface). Reads degrade gracefully (`[]`/`{}` + warning) rather than crashing. **Deferred:** limit/stop order types, `modify_order`, `protect` (stop/TP).

> **Operational note:** the adapter re-opens the chart tab per call; firing many calls in rapid succession can exhaust the Interceptor extension (tab-create timeouts), at which point reads degrade gracefully. Production tuning (single persistent tab, fewer re-opens) is a tracked fast-follow.

**CI vs live:** CI has no browser, so the adapter is unit-tested with a scripted fake driver (asserts the UI-action *sequence*). The real DOM is exercised by the **live Interceptor dogfood** — which confirmed, against a live session: read account balance/equity/PnL/margin + open positions; `place_order` (created a working order, Orders 0→1, double-submit guard held); `cancel_order` (Orders 1→0); `list_positions`/`list_orders` parsed correctly. close/flatten are unit-tested (live-exercising them requires a filled position).

## Safety

- **PAPER_ONLY** enforced at startup — `TVBRIDGE_TRADING_MODE` must be `paper`; otherwise the lifespan hook exits 1.
- **Mock-default broker mode** — no broker contact unless operator explicitly sets `TVBRIDGE_BROKER_MODE=real-paper` AND provides credentials.
- **Idempotency** prevents double-fire on Pine Script retries (same `alert_id` → same `order_id`).
- **Rate limiting** prevents runaway strategies (default 60 req/min per source IP).
- **Constant-time secret comparison** — `hmac.compare_digest` against `TVBRIDGE_TV_WEBHOOK_SECRET`.
- **TradingView IP allowlist** — defense-in-depth alongside the shared secret.
- **Bookkeeping journal** — every accepted alert lands in `research/entities/pattern/strategy-{name}.md` via the workspace bookkeeping CLI (graceful no-op if CLI not reachable).

## Autonomous operator (`operate`)

The bridge is not just a passive receiver — it ships a **self-operating control
loop** that constantly self-dogfoods and manages positions autonomously, so you
don't have to babysit it. The operator is a controller in the RCS sense:

| Control element | Operator realization |
|---|---|
| **Plant** | broker positions + the bridge pipeline state |
| **Controller** | the multi-rate tick loop (`operator/loop.py`) |
| **Shields** | `.control/policy.yaml` operator gates (paper-only, dogfood-precondition, hard-halt, position caps) |
| **Feedback** | the self-dogfood canary + the order ledger + structured-log journal |

### The dogfood-as-precondition interlock (the safety heart)

Every tick, the operator fires a synthetic `__canary__` alert through the **real**
dispatch pipeline and verifies it roundtrips. **If the canary fails, the operator
halts position management.** You never manage money on a pipeline you cannot
confirm works. This is P11 (Empirical Feedback Loop) crystallized into a runtime
interlock — not a ritual you remember to run, a precondition the loop enforces.

- **soft halt** — one canary failure halts *this tick*; auto-recovers when the canary next passes.
- **hard halt** — `--halt-after-failures` (default 3) consecutive failures triggers a STICKY halt. A subsequently-passing canary does **not** clear it; only `operate reset` (operator-acknowledged recovery) does. This stops an autonomous loop from silently resuming after an intermittent fault.

Canary orders use a reserved `strategy_name` (`__canary__`) and are filtered at
the single order-ledger write point, so the self-dogfood can never move the book
it is meant to verify.

### Multi-rate cadence (echoes the RCS L0/L1/L2 hierarchy)

| Rate | Every | Does |
|---|---|---|
| fast | tick | self-dogfood canary roundtrip ("is the pipeline alive?") |
| medium | `--medium-every` ticks (default 5) | read net positions; flag if open-position count exceeds `--max-open-positions` |
| slow | `--slow-every` ticks (default 1440 ≈ daily at 60s) | compute drift vs target allocation; report |

### Commands

```bash
operate tick        # one tick (cron / loop friendly). Exit 0 if canary passed, 1 otherwise.
operate run --interval 60   # continuous daemon
operate status      # print operator state as JSON
operate positions   # print net positions
operate reset       # clear a hard halt (operator-acknowledged recovery)
```

`operate tick` writes **clean JSON to stdout** (logs go to stderr), so
`operate tick | jq` works in scripts. State persists to
`~/.tradingview-bridge/operator-state.json` (override with
`TVBRIDGE_OPERATOR_STATE_PATH`), so the loop is **restart-safe** (P12): a cron, a
`/loop`, or a `persist iterate` all resume from the same on-disk state.

### Worked example (live)

```bash
$ operate tick | jq '{tick_count, last_canary_passed, mgmt: (.last_canary_passed and (.hard_halted|not))}'
{ "tick_count": 1, "last_canary_passed": true, "mgmt": true }

# Force the interlock: point the HTTP canary at a dead bridge
$ operate tick --probe-url http://127.0.0.1:59999 --halt-after-failures 3   # x3
{ "tick": 3, "canary": false, "consec_fail": 3, "hard_halted": true, "mgmt": false }

# A healthy canary does NOT clear a hard halt:
$ operate tick | jq '{canary: .last_canary_passed, hard_halted, mgmt}'
{ "canary": true, "hard_halted": true, "mgmt": false }

# Only reset does:
$ operate reset >/dev/null && operate tick | jq '.mgmt'
true
```

### Scheduling — pick the mechanism (P19 cube)

The operator loop is mechanism-agnostic. Wire it to whichever fits:

| Shape | Mechanism | How |
|---|---|---|
| in-session, internal | `/loop` | `/loop 60s operate tick` |
| across-session, cron | `schedule` / CronCreate | a routine firing `operate tick` every minute |
| across-session, external | `persist iterate` | `operate tick` in a `PROMPT.md`-driven restart loop |
| true daemon | launchd / systemd | a unit running `operate run --interval 60` |

A cron / `/loop` driving `operate tick` is the recommended default — each
invocation is a fresh process reading persisted state, which is the most
restart-resilient form (no in-process loop to decay over long horizons).

### Running autonomous against TradingView Paper (the closed loop)

```bash
export TVBRIDGE_BROKER_MODE=tradingview-paper
operate run --interval 60        # or: /loop 60s operate tick
```

Two safety properties make this loop safe to leave running against a **real**
(simulated) account:

1. **Read-only canary in real-venue mode.** When `broker_mode` is a real venue,
   the self-dogfood canary verifies the pipeline via `health_check()` only — it
   **never places an order**. (The place-an-order canary is used solely in
   `mock` mode.) *Proven live: 2 operator ticks in tradingview-paper mode placed
   **0** orders; the canary passed via `venue_health`.* Without this, the
   operator would drop a canary order every tick.
2. **Reconciliation against the real book.** Each medium tick the operator reads
   the actual TradingView positions (`list_positions`) and compares them to its
   own ledger. A position it did not place (`broker_only`) or one it believes
   open that the broker no longer shows (`ledger_only`) is surfaced via
   `operator_position_drift` — never silent.

The dogfood-as-precondition interlock still wraps everything: if the read-only
canary fails (venue unreachable), position management halts.

### What the operator does NOT do yet (deferred)

- **Auto-rebalance execution** — drift is *computed and reported*; the operator does not yet place corrective orders. (Next: gate-guarded auto-rebalance in paper mode.)
- **Real-paper broker position reads** — positions come from the order ledger (what the bridge dispatched), not from polling IBKR/Kraken. True reconciliation against broker state needs the real-paper SDK wiring (PR 2b).
- **Price-weighted drift / EGRI strategy-param optimization** — drift is in units, not value; target allocation is units per symbol. Price-weighted rebalancing composes this with the parent skill's `market_data.py` + `backtest.py` (a follow-up).

## Decision plane — strategies (`strategy/`)

The control plane (operator + adapter) *executes*; the decision plane *decides*.
Its keystone is a unified **Strategy** abstraction — a pure function
`signal(market_state) → Signal{enter/exit/size}` that drives **both** simulation
and live, so the same rules are measured in backtest and run through the live
operator. The gap between the two (backtest vs paper-forward) is the honest
signal of whether an edge is real.

```python
from tradingview_bridge.strategy import SMACrossover, run_backtest, signal_to_tvalert

# 1. define once
strat = SMACrossover(fast=50, slow=200)

# 2. measure in simulation
result = run_backtest(strat, bars, symbol="AAPL", asset_class="stock")
#   → BacktestResult(total_return_pct, sharpe, max_drawdown_pct, win_rate_pct, ...)

# 3. run live — the SAME strategy → a TVAlert → the operator → TradingView paper
alert = signal_to_tvalert(strat.signal(state), symbol="AAPL", asset_class="stock", ...)
```

**Components:** `types.py` (Bar / MarketState / Signal) · `base.py` (Strategy ABC,
deterministic) · `library.py` (SMACrossover / RSIMeanReversion / DonchianBreakout —
matching the Pine templates) · `tvalert.py` (Signal → TVAlert; `hold` → no alert) ·
`backtest_runner.py` (event-driven long-only backtest → metrics).

**Honesty:** the backtest runner is deliberately simple (long-only, full
allocation, fills at close, no costs). It measures a strategy's directional edge;
it does **not** model execution reality. **A good backtest means nothing until a
strategy survives walk-forward + out-of-sample + paper-forward** — which is the
evaluation plane below. This package is the inner loop those layers wrap.

## Evaluation plane — walk-forward + ledger (`evaluation/`)

The strategy plane can score *one* backtest. The evaluation plane turns that into
**trustworthy, anti-overfit evidence you can rank strategies on** — the numbers
the orchestration layer (and the agent's reasoning) allocate on. One lucky number
is not an edge; consistency across out-of-sample windows is.

```python
from tradingview_bridge.evaluation import (
    walk_forward, score_walk_forward, PerformanceLedger, EvaluationRecord,
)

# 1. walk-forward: partition a continuous backtest into N out-of-sample windows
wf = walk_forward(strat, bars, symbol="AAPL", asset_class="stock", n_windows=5)
#   → consistency_pct (% windows profitable), return_std (dispersion),
#     mean_sharpe, worst_window_return_pct, worst_window_drawdown_pct, windows[]

# 2. score: one 0-1 trustworthiness number, anti-overfit BY DESIGN
score = score_walk_forward(wf)        # consistency + robustness weigh HALF
#   → a dazzling mean-Sharpe strategy with inconsistent windows scores LOW

# 3. ledger: persist every evaluation, then compare backtest vs live-paper
#    (async — run inside an event loop, e.g. asyncio.run(record_and_compare()))
async def record_and_compare() -> None:
    ledger = PerformanceLedger()      # ~/.tradingview-bridge/performance.sqlite
    await ledger.record(EvaluationRecord(strategy=strat.name, symbol="AAPL",
        kind="walk_forward", return_pct=wf.mean_return_pct, sharpe=wf.mean_sharpe, ...))
    gap = await ledger.compare_sim_vs_live(strat.name, symbol="AAPL")  # SimLiveGap
    #   → return_gap_pct = live - sim; negative = backtest edge decayed in paper.
```

**Components:** `walk_forward.py` (continuous backtest → N windows →
`WalkForwardResult` with consistency + dispersion) · `score.py`
(`score_walk_forward` → `StrategyScore`; weights `risk_adjusted` 0.35,
`consistency` 0.30, `robustness` 0.20, `drawdown_safety` 0.15 — consistency +
robustness = **half** the score, the anti-overfit discipline made numeric) ·
`ledger.py` (`PerformanceLedger`, async SQLite; `compare_sim_vs_live` →
`SimLiveGap`, the backtest-vs-paper reality check).

**Anti-self-deception, not a profit promise.** The score's job is to *refuse to be
seduced by one lucky backtest* — a whipsaw strategy that loses across every window
correctly scores ~0.25, not 0.85. The system gives rigorous measurement; it does
**not** guarantee gains.

This package is the inner loop the **orchestration plane** wraps.

## Orchestration plane — autoresearch (`orchestrator/`)

The strategy plane *decides* per bar; the evaluation plane *measures* per
strategy; this plane *decides what to trust across strategies* — the agent's
**slow loop**. One tick: evaluate every strategy → record to the ledger → rank →
recommend an allocation, **tempered by live-paper reality and always human-gated**.

```python
from tradingview_bridge.orchestrator import AutoResearch

# one tick of the slow loop (paper-only, records to the performance ledger)
report = await AutoResearch().run(roster, bars, symbol="AAPL", asset_class="stock")
#   → report.leaderboard       — strategies ranked by trustworthiness (anti-overfit)
#   → report.recommendation    — promote_candidate | paper_forward | reject
#                                requires_human_approval is ALWAYS True
```

Or from the CLI:

```bash
research run --symbol AAPL                 # synthetic bars (deterministic) → leaderboard + rec
research run --symbol AAPL --bars-csv x.csv --json   # your bars, JSON out
research leaderboard --symbol AAPL         # recorded evaluation history
```

**The decision (`recommend`)** — pure function of the leaderboard. The best
strategy clears the **trust gate** (default 0.6) → `promote_candidate`; promising
but under the gate → `paper_forward`; far under → `reject`. There is no
`go_live` action: promotion to real capital is a separate human decision, and
`AllocationRecommendation` *cannot be constructed* with the human gate disabled
(it raises) — the safety invariant is enforced by the type, not by convention.

**The reality check (`runner`)** — the loop-closing step. For a
`promote_candidate`, the runner consults the ledger's `compare_sim_vs_live`: if a
strategy looked great in simulation but its live-paper return decayed beyond
tolerance, the recommendation is **demoted** to `paper_forward`. Measurements
feed decisions; decisions are tempered by what live-paper actually did. The
reality check can only ever *weaken* a recommendation — never push it past the
gate.

**Components:** `research.py` (pure: `evaluate_all` / `rank` / `recommend`, no
I/O, fully reproducible) · `runner.py` (`AutoResearch` — the stateful tick:
ledger + reality check) · `types.py` (`StrategyEvaluation` / `Leaderboard` /
`AllocationRecommendation`) · `cli.py` (the `research` entry point).

**Honest framing.** The orchestrator ranks and recommends; it never trades and
never allocates capital. Live market-data integration (`market_data.py`) is
deferred — v1 runs on provided or deterministic-synthetic bars; the orchestration
logic is independent of the bar source.

This plane ranks a fixed roster; the **optimization plane** below *evolves* the
params themselves.

## Optimization plane — EGRI (`optimize/`)

The evaluation plane scores one strategy; the orchestrator ranks a fixed roster;
this plane **evolves a strategy's parameters** — honestly. It is an EGRI loop
(Evaluator-Governed Recursive Improvement, composing with the `autoany` skill):

- **Mutable artifact** — the strategy parameters (SMA fast/slow, RSI length/bands,
  Donchian length).
- **Immutable evaluator** — `walk_forward` + `score_walk_forward`, **frozen across
  the search**. The stop-gradient guarantee: the optimizer can change the params,
  never the yardstick, so it cannot tune the scorer to fit the data.
- **Promotion policy** — `generalizes` iff the out-of-sample test score clears a
  floor AND the train→test gap is within tolerance. Always **human-gated**.

```bash
optimize run --family sma-crossover --symbol AAPL    # grid-search → best generalizing params
optimize run --family rsi-mean-reversion --json      # JSON; --bars-csv x.csv for your data
```

**Why the holdout is the whole point.** Grid-searching N param-sets and keeping
the best is a multiple-comparisons overfitting risk — even noise has an in-sample
winner. The walk-forward consistency metric helps, but the only honest defense is
a **test segment the search never saw**:

1. **train** segment → every candidate is scored; the winner is selected here, on
   train **only**.
2. **test** segment (holdout) → the winner is scored **exactly once**. No test-set
   selection.
3. **generalization gap** = train − test. A large positive gap means the in-sample
   winner overfit and did not hold up; the verdict says so regardless of how
   dazzling the train score was.

```python
from tradingview_bridge.optimize import optimize_walk_forward, SMA_CROSSOVER_SPACE

result = optimize_walk_forward(SMA_CROSSOVER_SPACE, bars, symbol="AAPL", asset_class="stock")
#   → result.best          — the train-winner's params (selection saw train only)
#   → result.test_score    — its out-of-sample score (the honest estimate)
#   → result.generalization_gap, result.generalizes  — the human-gated verdict
```

**Components:** `space.py` (`ParamSpace` + the 3 built-in spaces — the mutable
surface) · `search.py` (deterministic grid search; truncation is logged, never
silent) · `egri.py` (`optimize_walk_forward` — the train/test loop + gap) ·
`types.py` (`OptimizationResult`, human-gated by construction — it cannot be built
with the gate disabled) · `cli.py` (the `optimize` entry point).

**Honest framing.** The optimizer measures and recommends params with an honest
out-of-sample estimate; it never trades, never records, never auto-applies.
Auto-feeding optimized params into the orchestrator roster is the next
(human-gated) integration step.

**Deferred (the rest of the decision plane):** evolutionary / Bayesian search (v1
is grid) · auto-feeding optimized params to the roster (human-gated) ·
regime/market-study layer · short side + cost/slippage · `market_data.py` live-bar
integration. Promoting any strategy to live-paper capital is human-gated + P20
cross-review.

## See also

- `SKILL.md` (this repo) — parent skill
- [`broomva/finance-substrate`](https://github.com/broomva/finance-substrate) — tax substrate (Form 210, DIAN, TRM)
- [Broker selection ADR](https://github.com/broomva/workspace/blob/main/docs/specs/2026-05-22-broker-selection-cross-asset.html)
- [Linear ticket BRO-167](https://github.com/broomva/workspace/blob/main/tasks/bro-167-cross-asset-trading-platform.md) (platform) · BRO-1247 (autonomous operator)
