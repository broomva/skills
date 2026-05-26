# strategies/ — Pine Script alpha library + chart screencap helpers

Five Pine Script v5 strategy templates that fire webhook alerts to the
`tradingview-bridge` service in the format the receiver expects (matches
`TVAlert` schema in `src/tradingview_bridge/schemas.py`).

Each script:
- Declares as `strategy(...)` (not `indicator`) so it can fire entry/exit alerts
- Uses Pine's `alert_message` parameter on each `strategy.entry`/`strategy.exit`
- Emits JSON keyed to `alert_id`, `secret`, `strategy_name`, `asset_class`,
  `symbol`, `action`, `size`, `size_type`, `price_hint`, `time`
- Default qty type is `percent_of_equity` for sizing portability across symbols

## Templates

| File | Strategy | Asset class default | When to use |
|---|---|---|---|
| `pine/01-sma-crossover.pine` | Simple Moving Average crossover (50/200) | stock | Classic trend-follow baseline. Compare every new alpha against this. |
| `pine/02-rsi-mean-reversion.pine` | RSI overbought/oversold reversal | stock | Mean-reverting markets (ranging instruments, sideways regimes). |
| `pine/03-donchian-breakout.pine` | Donchian channel breakout (Turtle-style) | crypto | Trend-following with momentum filter; ages well across regimes. |
| `pine/04-bollinger-squeeze.pine` | Bollinger Band squeeze + breakout direction | fx | Volatility-compression strategies; fires after low-vol periods. |
| `pine/05-multi-timeframe-trend.pine` | MTF EMA alignment (3-timeframe confluence) | crypto | High-confluence entries; lower trade frequency, higher win rate. |

## Using a template with the bridge

1. **Copy the .pine into TradingView's Pine Editor** (TradingView web UI → Pine Editor → New).
2. **Replace `REPLACE_WITH_YOUR_TVBRIDGE_TV_WEBHOOK_SECRET`** in the alert message with your actual secret (from `.env`'s `TVBRIDGE_TV_WEBHOOK_SECRET`).
3. **Add to chart** → save as strategy.
4. **Create alert** on the strategy: Condition = `Strategy: Order fills`, Webhook URL = your service's public `/webhook` endpoint (e.g., via Cloudflare Tunnel: `https://<tunnel>/webhook`). Message = `{{strategy.order.alert_message}}` (Pine fills this from the script).
5. **Fire test alert** in TradingView → check the bridge logs for `alert_dispatched` event.

## Customizing per asset class

The `asset_class` field in the alert JSON determines which broker the
dispatcher routes to (per `services/tradingview-bridge/src/tradingview_bridge/dispatch.py:route_asset_class`):

- `stock` / `etf` / `bond` / `fx` → IBKR
- `crypto` → Kraken
- `prediction` → Polymarket

The default in each template matches the strategy's most natural fit
(see table above), but you can change a single line at the top:

```pinescript
ASSET_CLASS = "stock"  // ← change to "crypto", "fx", etc.
```

## Capturing chart screenshots on alert fire (Interceptor)

`scripts/capture_chart.sh` is a shell wrapper showing how to drive the
[Interceptor skill](https://github.com/broomva/Interceptor) to capture a
TradingView chart screenshot at the moment an alert fires. This is the
P11 evidence layer for the dogfood pattern — visual proof the strategy
fired AND the chart context that produced it.

Usage:
```bash
./scripts/capture_chart.sh <chart_url> <output_path>
# e.g.:
./scripts/capture_chart.sh "https://www.tradingview.com/chart/?symbol=AAPL" /tmp/aapl-alert-001.png
```

The helper expects the Interceptor browser extension to be installed and
active. See `~/.claude/skills/Interceptor/SKILL.md` for setup.

## Why these five and not others

The five templates span the four core market regimes (trend, range, breakout,
volatility) plus a confluence pattern. They are deliberately **simple
baselines, not edge-edge strategies**:

- A new contributor should be able to read each in <5 minutes
- Each has clear entry/exit rules with no hidden state
- Each is unit-testable in TradingView's backtest replay
- Each fires alerts cleanly via the same JSON schema

Alpha-edge strategies (factor models, statistical arbitrage, market-making)
belong elsewhere — the `investment-management/scripts/` quantitative toolkit
(backtest.py, factor_analysis.py, optimizer) is the place for those.

The Pine library is the **last-mile signal layer**, not the alpha generator.

## See also

- Parent service: [`../README.md`](../README.md)
- Schema contract: [`../src/tradingview_bridge/schemas.py`](../src/tradingview_bridge/schemas.py)
- Dispatcher routing: [`../src/tradingview_bridge/dispatch.py`](../src/tradingview_bridge/dispatch.py)
- Workspace ADR (broker selection): [`docs/specs/2026-05-22-broker-selection-cross-asset.html`](https://github.com/broomva/workspace/blob/main/docs/specs/2026-05-22-broker-selection-cross-asset.html)
