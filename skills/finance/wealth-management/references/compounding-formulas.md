# Compounding & Growth Formulas

## Core Formulas

### Future Value with Regular Contributions
```
FV = PV × (1 + r)^n + PMT × [((1+r)^n - 1) / r]

PV  = present value (starting capital)
r   = periodic return rate (annual or monthly)
n   = number of periods
PMT = periodic contribution
```

### Compound Annual Growth Rate (CAGR)
```
CAGR = (FV / PV)^(1/n) - 1
```

### Real Return (Fisher Equation)
```
Real Return = (1 + nominal) / (1 + inflation) - 1
≈ nominal - inflation  (for small values)
```

### Rule of 72
```
Years to double ≈ 72 / annual_return_pct
At 7% return: 72/7 ≈ 10.3 years to double
```

### Required Monthly Savings
```
PMT = (FV - PV × (1+r_m)^n) × r_m / ((1+r_m)^n - 1)

r_m = monthly rate = (1 + annual_rate)^(1/12) - 1
n   = months
```

## Risk-Adjusted Metrics

### Sharpe Ratio
```
Sharpe = (R_p - R_f) / σ_p

R_p = portfolio return
R_f = risk-free rate (CDT 90 days or TES)
σ_p = portfolio standard deviation
```

### Maximum Drawdown
```
MDD = (Peak - Trough) / Peak × 100%
```

### Coefficient of Variation
```
CV = σ / μ
Lower CV = more consistent returns
```

## Tax Drag

### After-Tax Return
```
R_after_tax = R_nominal × (1 - effective_tax_rate)

For Colombian persona natural:
- Rendimientos financieros: ~33% marginal rate (if in top bracket)
- But INCR (componente inflacionario) ~50.88% is non-taxable
- Effective tax on rendimientos: ~33% × 49.12% ≈ 16.2%
```

### Tax-Deferred Compounding Advantage
```
After n years:
  Taxable:      PV × (1 + r × (1-t))^n
  Tax-deferred: PV × (1 + r)^n × (1 - t)

Advantage grows exponentially with n.
At r=7%, t=16%, n=20:
  Taxable:      PV × (1.0588)^20 = PV × 3.13
  Tax-deferred: PV × (1.07)^20 × 0.84 = PV × 3.25
  Advantage: 3.8% more wealth
```

## Monte Carlo Parameters

### Log-Normal Distribution
```
Monthly return: r_m ~ N(μ, σ²)
μ = expected monthly return = (1 + annual_return)^(1/12) - 1
σ = monthly volatility = annual_vol / √12
```

### Historical Volatilities (Annualized)

| Asset Class | Volatility | Notes |
|-------------|-----------|-------|
| Colombian equities (COLCAP) | 18-22% | Higher than developed markets |
| US equities (S&P 500) | 15-18% | Long-term average |
| Colombian bonds (TES) | 5-8% | Government bonds |
| CDT rates | 1-3% | Virtually no volatility |
| Real estate (Colombia) | 8-12% | Illiquid, smoothed |
| USD/COP (TRM) | 10-15% | FX risk for USD holders |

### Success Probability Thresholds

| Probability | Interpretation |
|-------------|---------------|
| > 85% | High confidence — maintain strategy |
| 70-85% | Good — monitor and adjust if drift |
| 50-70% | Moderate — consider increasing savings or reducing target |
| < 50% | At risk — needs intervention (more savings, longer horizon, higher risk) |
