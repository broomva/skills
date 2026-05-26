# wealth-management

Wealth management, financial planning, and investment analytics skill for Colombian residents. Compounds on [finance-substrate](https://github.com/broomva/finance-substrate) for tax-optimized wealth building.

## Quick Start

```bash
# Install
npx skills add broomva/wealth-management -y -g

# Portfolio summary (uses finance-substrate data)
python3 scripts/portfolio_summary.py --year 2024

# 20-year compound growth projection
python3 scripts/project_wealth.py --years 20 --monthly-contribution-usd 2000

# Goal planning (when do I reach $500K USD?)
python3 scripts/goal_planner.py --target-usd 500000 --target-date 2040-01-01
```

## Modes

| Mode | Script | Analytics Type |
|------|--------|---------------|
| `summary` | `portfolio_summary.py` | Descriptive |
| `project` | `project_wealth.py` | Predictive |
| `goal` | `goal_planner.py` | Predictive |
| `allocation` | `allocate_assets.py` | Prescriptive |
| `rebalance` | `rebalance.py` | Prescriptive |
| `scenario` | `scenario_analysis.py` | Predictive |
| `optimize` | `optimize_strategy.py` | Prescriptive |

## Dependencies

- Python 3.10+
- `finance-substrate` skill (data layer)
- No paid services. All data stays local.
