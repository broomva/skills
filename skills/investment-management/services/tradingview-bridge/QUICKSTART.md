# tradingview-bridge — Quickstart

The fast path from zero to the full **self-improving decision loop**, for a new
agent (or human). Task-oriented; for architecture and deep reference see
[README.md](./README.md).

> **What this is, in one breath.** A *paper-only, human-gated* trading control
> system. It **measures, optimizes, and recommends** strategies — it never moves
> live capital on its own. Two layers install: the **skill** (decision frameworks,
> loaded into an agent) and this **service** (4 CLIs + a webhook). The whole
> *decision plane* runs on synthetic or CSV bars with **no browser and no broker**;
> only live *execution* needs the browser surface.

---

## The dependency chain (what installs on what)

```text
npx skills add  →  investment-management skill  (SKILL.md + frameworks)
                     └── services/tradingview-bridge/   (this Python package, uv)
                           ├── 4 console scripts:  operate · research · optimize · roster
                           ├── FastAPI webhook:    tradingview_bridge.app
                           └── live-only deps (optional):
                                 ├── Interceptor CLI + logged-in Chrome → TradingView Paper
                                 └── broker SDKs + TWS/Kraken creds      → real-paper (KYC-gated)
```

The thing to internalise first: **`research` / `optimize` / `roster` need none of
the live deps.** They are pure Python over bars you supply. You can run the entire
measure → optimize → promote loop immediately after `uv sync`.

---

## 1. Install

```bash
# (a) the skill — loads SKILL.md + frameworks into the agent, and brings this service
npx skills add broomva/skills --skill investment-management
#     …or just clone the monorepo:  gh repo clone broomva/skills

# (b) the service — set up the Python env + the 4 console scripts
cd skills/investment-management/services/tradingview-bridge
uv sync --extra dev                  # core only; add --extra brokers for real-paper SDKs
cp .env.example .env                 # then set TVBRIDGE_TV_WEBHOOK_SECRET

# verify the install (the same gates CI runs)
uv run pytest -q
uv run ruff check . && uv run mypy src
```

`uv run <script>` works from the service directory without activating a venv. (After
`uv sync`, the four scripts — `operate`, `research`, `optimize`, `roster` — are also
on the venv `PATH`.)

---

## Path A — the decision loop in 60 seconds (no browser, no broker)

This is the heart of the system. Every command writes a human table to stdout, or
clean JSON with `--json` (logs always go to stderr, so `… --json | jq` is safe).

```bash
# 1. EVALUATE — walk-forward + anti-overfit score → leaderboard + (human-gated) recommendation
uv run research run --symbol AAPL

# 2. OPTIMIZE — EGRI param search with a TRUE train/test holdout → best *generalizing* params
uv run optimize run --family sma-crossover

# 3. PROPOSE — record the optimizer winner, automatically, but ONLY if it cleared
#    the out-of-sample holdout (overfit winners are never proposed)
uv run roster propose --family sma-crossover
uv run roster list --status proposed          # review the candidate + its OOS evidence

# 4. PROMOTE — the HUMAN gate: proposed → active
uv run roster promote 1

# 5. COMPOSE — the orchestrator now measures the optimized params instead of the defaults
uv run research run --symbol AAPL --roster-db ~/.tradingview-bridge/roster.sqlite
```

Use your own price history anywhere bars are taken: `--bars-csv yourfile.csv` (a CSV
with at least a `close` column; OHLCV optional). The synthetic generator is
deterministic, so a run is reproducible.

That five-step sequence **is** the self-improving loop:

```text
optimize → propose (auto, OOS-gated) → promote (HUMAN) → orchestrator measures
optimized params → recommendation (still human-gated) → [allocate: HUMAN] → capital
```

---

## Path B — live TradingView Paper execution (zero KYC, zero capital)

For real (simulated) execution under autonomous control, add the browser surface.
TradingView has no inbound trading API, so the bridge drives its built-in **Paper
Trading** simulator through the [Interceptor](https://github.com/Hacker-Valley-Media/slop-browser)
CLI (real Chrome, your logged-in session).

```bash
# one-time: Interceptor extension active in Chrome, logged into TradingView,
#           Paper Trading connected in the Trading Panel.

export TVBRIDGE_TRADING_MODE=paper                 # PAPER_ONLY — the app exits 1 if this isn't 'paper'
export TVBRIDGE_TV_WEBHOOK_SECRET=$(openssl rand -hex 32)
export TVBRIDGE_BROKER_MODE=tradingview-paper      # all alerts → TradingView's simulator

uv run uvicorn tradingview_bridge.app:app --port 8787   # the webhook receiver
uv run operate run --interval 60                         # the autonomous operator
```

TradingView Alerts POST a Pine Script JSON payload to `/webhook` (template in the
[README](./README.md#tradingview-pine-script-alert-template)); the operator manages
the book each tick under a **dogfood-as-precondition interlock** (it self-checks the
dispatch pipeline read-only every tick and halts position management if that canary
fails). Scheduling follows the P19 cube — `/loop 60s operate tick`, a cron firing
`operate tick`, or `persist iterate` (state is on disk, so the loop is restart-safe).

Leave `TVBRIDGE_BROKER_MODE` unset (the **mock** default) to exercise the full
pipeline with zero external contact — useful for wiring + tests.

---

## The five workflows

| Workflow | Command | Role |
|---|---|---|
| **Execute** | `operate tick` · `operate run` · the webhook | drive TradingView Paper (or mock) under the interlock |
| **Evaluate** | `research run` | walk-forward + anti-overfit score → leaderboard, tempered by live-paper reality |
| **Optimize** | `optimize run` | EGRI — evolve params on a true train/test holdout (`generalizes` verdict) |
| **Promote** | `roster propose` · `roster promote` · `roster list` · `roster active` | the human-gated bridge: OOS-validated params → the orchestrator's roster |
| **Compose** | `research run --roster-db …` | the loop closing on itself |

Each CLI has `--help`; each `run`-style command takes `--json`.

---

## The safety model (read this before going live)

The system is built so an agent **cannot** move capital by accident:

- **PAPER_ONLY** — enforced at startup; the process exits if `TVBRIDGE_TRADING_MODE != paper`.
- **Mock-default** — no broker or browser contact unless you explicitly set
  `TVBRIDGE_BROKER_MODE` *and* provide the surface (credentials / a logged-in session).
- **Two independent human gates** between an optimizer result and capital:
  1. `propose` is automatic but records candidates as `proposed` only when they pass
     the out-of-sample holdout — **no automatic path ever sets a roster entry `active`**.
  2. `promote` (`proposed → active`) is a human action; and even an active roster only
     changes what the orchestrator **measures** — its recommendation is always
     `requires_human_approval=True`. Capital needs a second, separate human decision.
- **Idempotency + rate limiting + constant-time secret comparison** on the webhook.

The honest summary: this is **measurement and recommendation, never a go-live.** No
CLI in this package places live capital.

---

## Where to go deeper

| You want… | See |
|---|---|
| Architecture, the decision-plane layers, the RCS framing | [README.md](./README.md) |
| The autonomous operator + the interlock + scheduling | [README — Autonomous operator](./README.md#autonomous-operator-operate) |
| Evaluation / orchestration / optimization / roster internals | [README — decision-plane sections](./README.md#decision-plane--strategies-strategy) |
| TradingView Paper control details (selectors, order lifecycle) | [README — TradingView Paper Trading mode](./README.md#tradingview-paper-trading-mode-tradingview-paper) |
| The full skill (frameworks, philosophies, modes) | [../../SKILL.md](../../SKILL.md) |

---

## What's real vs deferred

- ✅ **Works after `uv sync`:** the full decision plane (`research` / `optimize` /
  `roster`) on synthetic or CSV bars — pure Python, no external deps.
- ✅ **Works with browser setup:** live TradingView Paper execution via Interceptor
  (proven against a live session: place / cancel / list / close).
- ⏳ **Deferred:** `market_data.py` (live bar feeds — today you supply bars) ·
  real-broker SDKs (IBKR / Kraken, KYC-gated) · scheduler-driven auto-propose ·
  evolutionary search · short side + cost/slippage.
