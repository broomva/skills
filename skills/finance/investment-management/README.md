# investment-management

Full-stack investment management skill: from philosophy to execution. Research, analyze, decide, execute, track, and optimize across traditional and alternative asset classes.

Compounds on [finance-substrate](https://github.com/broomva/finance-substrate) (accounting/tax) and [wealth-management](https://github.com/broomva/wealth-management) (projections/goals) for a complete financial management framework.

## Quick Start

```bash
# Install
npx skills add broomva/skills --skill investment-management -y -g

# Market data (always works, no dependencies)
python3 scripts/market_data.py --trm

# With yfinance installed: pip install yfinance
python3 scripts/market_data.py --ticker AAPL --type price --period 1y
python3 scripts/screener.py --philosophy value --universe custom --tickers AAPL,MSFT,JPM,BAC,KO
python3 scripts/scorer.py --ticker AAPL --philosophy balanced
```

## Modes

| # | Mode | Script | Type | Status |
|---|------|--------|------|--------|
| 1 | `screen` | `screener.py` | Screening | Working |
| 2 | `research` | `research.py` | Analysis | Planned |
| 3 | `factor` | `factor_analysis.py` | Quant | Planned |
| 4 | `backtest` | `backtest.py` | Quant | Working |
| 5 | `optimize` | `portfolio_optimizer.py` | Quant | Planned |
| 6 | `risk` | `risk_analysis.py` | Analysis | Planned |
| 7 | `trade` | `trade.py` | Execution | Planned |
| 8 | `track` | `tracker.py` | Tracking | Planned |
| 9 | `rebalance` | `rebalancer.py` | Execution | Planned |
| 10 | `data` | `market_data.py` | Data | Working |
| 11 | `score` | `scorer.py` | Analysis | Working |

## Investment Philosophies

Built-in scoring and screening frameworks from legendary investors:

- **Value** (Graham/Buffett): Margin of safety, moats, owner earnings
- **Quality** (Munger): ROIC, margin stability, debt discipline
- **Growth** (Lynch): PEG ratio, tenbaggers, revenue acceleration
- **Systematic** (Dalio/AQR): Factor exposure, risk parity, All-Weather
- **Passive** (Bogle): Three-fund portfolio, low-cost indexing
- **Barbell** (Taleb): 85% ultra-safe + 15% high-convexity

## Dependencies

- Python 3.10+ (core scripts work with stdlib only)
- `yfinance` — Stock data (optional, `pip install yfinance`)
- `pycoingecko` — Crypto data (optional, `pip install pycoingecko`)
- `fredapi` — Macro data (optional, `pip install fredapi`)
- No paid services required. All data stays local.
