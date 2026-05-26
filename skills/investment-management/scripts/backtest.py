#!/usr/bin/env python3
"""
Strategy Backtesting Engine (Mode 4) — investment-management skill.

Test investment strategies against historical data. Supports built-in strategies
(buy-and-hold, equal-weight, risk parity, momentum, value, all-weather) and
custom YAML-defined strategies. Outputs structured metrics consumable by
autoany EGRI evaluator loops.

Usage:
    python3 backtest.py --strategy buy-and-hold --tickers SPY --period 10y
    python3 backtest.py --strategy equal-weight --tickers SPY,QQQ,BND,GLD --period 5y
    python3 backtest.py --strategy risk-parity --tickers SPY,TLT,GLD,VNQ --period 10y
    python3 backtest.py --strategy momentum --tickers SPY,QQQ,EEM,TLT,GLD --top 3 --period 5y
    python3 backtest.py --strategy-file strategy.yaml --period 10y
    python3 backtest.py --strategy all-weather --period 10y --json
    python3 backtest.py --strategy buy-and-hold --tickers SPY --period 10y --benchmark SPY

EGRI evaluator mode (structured JSON output for autoany):
    python3 backtest.py --strategy-file strategy.yaml --period 10y --egri
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Optional dependencies
# ---------------------------------------------------------------------------
_yfinance = None
_np = None
_yaml = None

try:
    import yfinance as _yfinance
except ImportError:
    pass

try:
    import numpy as _np
except ImportError:
    pass

try:
    import yaml as _yaml
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE = 0.04  # ~4% (current US T-bill rate)
CACHE_DIR = Path.home() / ".investment-management" / "market-data" / "prices"

# Dalio's All-Weather allocation
ALL_WEATHER = {
    "SPY": 0.30,   # US equities
    "TLT": 0.40,   # Long-term bonds
    "IEF": 0.15,   # Intermediate bonds
    "GLD": 0.075,  # Gold
    "DBC": 0.075,  # Commodities
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BacktestMetrics:
    """Core metrics from a backtest run."""
    strategy: str
    tickers: list[str]
    period: str
    start_date: str
    end_date: str
    trading_days: int
    years: float
    # Returns
    total_return_pct: float
    cagr_pct: float
    # Risk-adjusted
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    # Risk
    annualized_volatility_pct: float
    max_drawdown_pct: float
    max_drawdown_start: str
    max_drawdown_end: str
    max_drawdown_recovery: str | None
    # Win/loss
    win_rate_pct: float
    avg_daily_return_pct: float
    avg_winning_day_pct: float
    avg_losing_day_pct: float
    best_day_pct: float
    worst_day_pct: float
    # Portfolio
    starting_value: float
    ending_value: float
    weights: dict[str, float]
    rebalance_count: int

    def to_egri_outcome(self) -> dict:
        """Format as autoany EGRI Outcome for evaluator consumption."""
        return {
            "score": self.sharpe_ratio,
            "constraints_passed": self.max_drawdown_pct > -15.0,
            "violations": (
                [f"max_drawdown={self.max_drawdown_pct:.1f}% exceeds -15% limit"]
                if self.max_drawdown_pct <= -15.0 else []
            ),
            "metrics": {
                "sharpe_ratio": self.sharpe_ratio,
                "sortino_ratio": self.sortino_ratio,
                "calmar_ratio": self.calmar_ratio,
                "cagr_pct": self.cagr_pct,
                "max_drawdown_pct": self.max_drawdown_pct,
                "volatility_pct": self.annualized_volatility_pct,
                "total_return_pct": self.total_return_pct,
                "win_rate_pct": self.win_rate_pct,
            },
        }


@dataclass
class StrategyConfig:
    """Strategy definition — can be loaded from YAML or built-in."""
    name: str
    tickers: list[str]
    weights: dict[str, float]
    rebalance_frequency: str = "quarterly"  # daily, monthly, quarterly, annually, never
    rebalance_threshold_pct: float = 5.0
    momentum_lookback: int = 252  # trading days for momentum calc
    momentum_top_n: int = 3
    stop_loss_pct: float | None = None
    # For value strategy
    value_metric: str = "pe_ratio"  # pe_ratio, pb_ratio, fcf_yield


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def _parse_period(period: str) -> tuple[datetime, datetime]:
    """Convert period string like '5y', '10y', '3m', '1y' to date range."""
    end = datetime.now()
    val = int(period[:-1])
    unit = period[-1].lower()
    if unit == "y":
        start = end - timedelta(days=val * 365)
    elif unit == "m":
        start = end - timedelta(days=val * 30)
    elif unit == "d":
        start = end - timedelta(days=val)
    else:
        start = end - timedelta(days=val * 365)
    return start, end


def fetch_prices(tickers: list[str], period: str) -> dict[str, list[tuple[str, float]]]:
    """Fetch adjusted close prices for tickers. Returns {ticker: [(date_str, price), ...]}."""
    if _yfinance is None:
        print("Error: yfinance required. Install with: pip install yfinance", file=sys.stderr)
        raise SystemExit(1)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    result = {}

    for ticker in tickers:
        cache_file = CACHE_DIR / f"{ticker}_{period}.json"
        cache_fresh = False

        if cache_file.exists():
            age_hours = (datetime.now().timestamp() - cache_file.stat().st_mtime) / 3600
            if age_hours < 24:
                cache_fresh = True
                with open(cache_file) as f:
                    result[ticker] = json.load(f)

        if not cache_fresh:
            try:
                data = _yfinance.download(ticker, period=period, progress=False, auto_adjust=True)
                if data.empty:
                    print(f"Warning: no data for {ticker}", file=sys.stderr)
                    continue
                prices = []
                for idx, row in data.iterrows():
                    date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
                    close = float(row["Close"]) if not _np or not _np.isnan(float(row["Close"])) else None
                    if close is not None:
                        prices.append((date_str, close))
                result[ticker] = prices
                with open(cache_file, "w") as f:
                    json.dump(prices, f)
            except Exception as e:
                print(f"Warning: failed to fetch {ticker}: {e}", file=sys.stderr)

    return result


def align_prices(price_data: dict[str, list[tuple[str, float]]]) -> tuple[list[str], dict[str, list[float]]]:
    """Align all tickers to the same dates. Returns (dates, {ticker: [prices]})."""
    # Find common dates
    date_sets = [set(d for d, _ in prices) for prices in price_data.values()]
    if not date_sets:
        return [], {}
    common_dates = sorted(set.intersection(*date_sets))

    # Build aligned price arrays
    aligned = {}
    for ticker, prices in price_data.items():
        price_map = dict(prices)
        aligned[ticker] = [price_map[d] for d in common_dates]

    return common_dates, aligned


# ---------------------------------------------------------------------------
# Portfolio simulation
# ---------------------------------------------------------------------------

def compute_portfolio_returns(
    dates: list[str],
    prices: dict[str, list[float]],
    config: StrategyConfig,
) -> tuple[list[float], list[float], int]:
    """
    Simulate portfolio returns given prices and strategy config.
    Returns (daily_returns, portfolio_values, rebalance_count).
    """
    tickers = [t for t in config.tickers if t in prices]
    if not tickers:
        return [], [], 0

    n_days = len(dates)
    weights = _normalize_weights({t: config.weights.get(t, 0) for t in tickers})

    # Initialize portfolio
    initial_value = 10000.0
    holdings = {t: initial_value * weights[t] / prices[t][0] for t in tickers}
    portfolio_values = [initial_value]
    daily_returns = []
    rebalance_count = 0

    # Rebalance schedule
    last_rebalance_month = None
    last_rebalance_quarter = None

    for i in range(1, n_days):
        # Compute current portfolio value
        value = sum(holdings[t] * prices[t][i] for t in tickers)
        prev_value = portfolio_values[-1]
        daily_ret = (value - prev_value) / prev_value if prev_value > 0 else 0
        daily_returns.append(daily_ret)
        portfolio_values.append(value)

        # Stop loss check
        if config.stop_loss_pct is not None:
            peak = max(portfolio_values)
            drawdown = (value - peak) / peak
            if drawdown < config.stop_loss_pct / 100.0:
                # Liquidate to cash — hold flat
                for t in tickers:
                    holdings[t] = 0
                continue

        # Check rebalance trigger
        should_rebalance = False
        date_str = dates[i]

        if config.rebalance_frequency == "daily":
            should_rebalance = True
        elif config.rebalance_frequency == "monthly":
            month = date_str[:7]
            if month != last_rebalance_month:
                should_rebalance = True
                last_rebalance_month = month
        elif config.rebalance_frequency == "quarterly":
            quarter = date_str[:4] + "Q" + str((int(date_str[5:7]) - 1) // 3)
            if quarter != last_rebalance_quarter:
                should_rebalance = True
                last_rebalance_quarter = quarter
        elif config.rebalance_frequency == "annually":
            year = date_str[:4]
            if last_rebalance_month is None or year != last_rebalance_month:
                should_rebalance = True
                last_rebalance_month = year

        # Threshold check — only rebalance if drift exceeds threshold
        if should_rebalance and config.rebalance_threshold_pct > 0:
            current_weights = {t: holdings[t] * prices[t][i] / value for t in tickers}
            max_drift = max(abs(current_weights[t] - weights[t]) for t in tickers)
            if max_drift * 100 < config.rebalance_threshold_pct:
                should_rebalance = False

        if should_rebalance and config.rebalance_frequency != "never":
            # For momentum strategy, update weights
            if config.name == "momentum" and i >= config.momentum_lookback:
                momentum_scores = {}
                for t in tickers:
                    if i >= config.momentum_lookback:
                        ret = (prices[t][i] / prices[t][i - config.momentum_lookback]) - 1
                        momentum_scores[t] = ret
                top_n = sorted(momentum_scores, key=momentum_scores.get, reverse=True)[:config.momentum_top_n]
                weights = {t: (1.0 / config.momentum_top_n if t in top_n else 0) for t in tickers}

            # Rebalance holdings
            for t in tickers:
                holdings[t] = value * weights[t] / prices[t][i] if prices[t][i] > 0 else 0
            rebalance_count += 1

    return daily_returns, portfolio_values, rebalance_count


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    """Normalize weights to sum to 1.0."""
    total = sum(weights.values())
    if total == 0:
        n = len(weights)
        return {t: 1.0 / n for t in weights}
    return {t: w / total for t, w in weights.items()}


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------

def compute_metrics(
    strategy_name: str,
    tickers: list[str],
    weights: dict[str, float],
    period: str,
    dates: list[str],
    daily_returns: list[float],
    portfolio_values: list[float],
    rebalance_count: int,
) -> BacktestMetrics:
    """Compute all backtest metrics from daily returns."""
    n = len(daily_returns)
    if n == 0:
        return _empty_metrics(strategy_name, tickers, weights, period)

    years = n / TRADING_DAYS_PER_YEAR

    # Returns
    total_return = (portfolio_values[-1] / portfolio_values[0]) - 1
    cagr = (portfolio_values[-1] / portfolio_values[0]) ** (1 / years) - 1 if years > 0 else 0

    # Volatility
    mean_ret = sum(daily_returns) / n
    variance = sum((r - mean_ret) ** 2 for r in daily_returns) / (n - 1) if n > 1 else 0
    daily_vol = math.sqrt(variance)
    ann_vol = daily_vol * math.sqrt(TRADING_DAYS_PER_YEAR)

    # Downside deviation (for Sortino)
    downside_returns = [min(0, r - RISK_FREE_RATE / TRADING_DAYS_PER_YEAR) for r in daily_returns]
    downside_var = sum(r ** 2 for r in downside_returns) / n if n > 0 else 0
    downside_dev = math.sqrt(downside_var) * math.sqrt(TRADING_DAYS_PER_YEAR)

    # Sharpe ratio
    excess_return = cagr - RISK_FREE_RATE
    sharpe = excess_return / ann_vol if ann_vol > 0 else 0

    # Sortino ratio
    sortino = excess_return / downside_dev if downside_dev > 0 else 0

    # Max drawdown
    peak = portfolio_values[0]
    max_dd = 0
    dd_start_idx = 0
    dd_end_idx = 0
    current_dd_start = 0
    recovery_idx = None

    for i, val in enumerate(portfolio_values):
        if val > peak:
            peak = val
            current_dd_start = i
        dd = (val - peak) / peak
        if dd < max_dd:
            max_dd = dd
            dd_start_idx = current_dd_start
            dd_end_idx = i

    # Find recovery point
    if dd_end_idx < len(portfolio_values) - 1:
        peak_at_dd = portfolio_values[dd_start_idx]
        for i in range(dd_end_idx, len(portfolio_values)):
            if portfolio_values[i] >= peak_at_dd:
                recovery_idx = i
                break

    # Calmar ratio
    calmar = cagr / abs(max_dd) if max_dd != 0 else 0

    # Win/loss stats
    winning = [r for r in daily_returns if r > 0]
    losing = [r for r in daily_returns if r < 0]
    win_rate = len(winning) / n * 100 if n > 0 else 0

    return BacktestMetrics(
        strategy=strategy_name,
        tickers=tickers,
        period=period,
        start_date=dates[0] if dates else "",
        end_date=dates[-1] if dates else "",
        trading_days=n,
        years=round(years, 2),
        total_return_pct=round(total_return * 100, 2),
        cagr_pct=round(cagr * 100, 2),
        sharpe_ratio=round(sharpe, 3),
        sortino_ratio=round(sortino, 3),
        calmar_ratio=round(calmar, 3),
        annualized_volatility_pct=round(ann_vol * 100, 2),
        max_drawdown_pct=round(max_dd * 100, 2),
        max_drawdown_start=dates[dd_start_idx] if dates else "",
        max_drawdown_end=dates[dd_end_idx] if dates else "",
        max_drawdown_recovery=dates[recovery_idx] if recovery_idx is not None and dates else None,
        win_rate_pct=round(win_rate, 1),
        avg_daily_return_pct=round(mean_ret * 100, 4),
        avg_winning_day_pct=round(sum(winning) / len(winning) * 100, 4) if winning else 0,
        avg_losing_day_pct=round(sum(losing) / len(losing) * 100, 4) if losing else 0,
        best_day_pct=round(max(daily_returns) * 100, 2),
        worst_day_pct=round(min(daily_returns) * 100, 2),
        starting_value=round(portfolio_values[0], 2),
        ending_value=round(portfolio_values[-1], 2),
        weights=weights,
        rebalance_count=rebalance_count,
    )


def _empty_metrics(name: str, tickers: list[str], weights: dict, period: str) -> BacktestMetrics:
    return BacktestMetrics(
        strategy=name, tickers=tickers, period=period,
        start_date="", end_date="", trading_days=0, years=0,
        total_return_pct=0, cagr_pct=0, sharpe_ratio=0, sortino_ratio=0, calmar_ratio=0,
        annualized_volatility_pct=0, max_drawdown_pct=0, max_drawdown_start="",
        max_drawdown_end="", max_drawdown_recovery=None,
        win_rate_pct=0, avg_daily_return_pct=0, avg_winning_day_pct=0, avg_losing_day_pct=0,
        best_day_pct=0, worst_day_pct=0, starting_value=0, ending_value=0,
        weights=weights, rebalance_count=0,
    )


# ---------------------------------------------------------------------------
# Strategy builders
# ---------------------------------------------------------------------------

def build_strategy(name: str, tickers: list[str], **kwargs) -> StrategyConfig:
    """Build a strategy config from a named preset."""
    if name == "buy-and-hold":
        weights = {tickers[0]: 1.0} if len(tickers) == 1 else {t: 1.0 / len(tickers) for t in tickers}
        return StrategyConfig(name=name, tickers=tickers, weights=weights, rebalance_frequency="never")

    elif name == "equal-weight":
        weights = {t: 1.0 / len(tickers) for t in tickers}
        return StrategyConfig(name=name, tickers=tickers, weights=weights, rebalance_frequency="quarterly")

    elif name == "risk-parity":
        # Inverse-volatility weighting — computed from data in the simulation
        # Start equal, will be dynamically adjusted if data allows
        weights = {t: 1.0 / len(tickers) for t in tickers}
        return StrategyConfig(name=name, tickers=tickers, weights=weights, rebalance_frequency="quarterly")

    elif name == "momentum":
        weights = {t: 1.0 / len(tickers) for t in tickers}
        top_n = kwargs.get("top", min(3, len(tickers)))
        return StrategyConfig(
            name=name, tickers=tickers, weights=weights,
            rebalance_frequency="monthly", momentum_top_n=top_n,
        )

    elif name == "all-weather":
        tickers_aw = list(ALL_WEATHER.keys())
        return StrategyConfig(
            name=name, tickers=tickers_aw, weights=dict(ALL_WEATHER),
            rebalance_frequency="quarterly",
        )

    elif name == "custom":
        weights = kwargs.get("weights", {t: 1.0 / len(tickers) for t in tickers})
        freq = kwargs.get("rebalance_frequency", "quarterly")
        threshold = kwargs.get("rebalance_threshold_pct", 5.0)
        stop_loss = kwargs.get("stop_loss_pct", None)
        return StrategyConfig(
            name=name, tickers=tickers, weights=weights,
            rebalance_frequency=freq, rebalance_threshold_pct=threshold,
            stop_loss_pct=stop_loss,
        )

    else:
        # Default to equal-weight
        weights = {t: 1.0 / len(tickers) for t in tickers}
        return StrategyConfig(name=name, tickers=tickers, weights=weights, rebalance_frequency="quarterly")


def load_strategy_yaml(path: str) -> StrategyConfig:
    """Load strategy from a YAML file (autoany artifact format)."""
    with open(path) as f:
        if _yaml:
            data = _yaml.safe_load(f)
        else:
            # Minimal YAML-like parser for simple configs
            data = _parse_simple_yaml(f.read())

    return StrategyConfig(
        name=data.get("name", "custom"),
        tickers=list(data.get("weights", {}).keys()) or data.get("tickers", []),
        weights=data.get("weights", {}),
        rebalance_frequency=data.get("rebalance", {}).get("frequency", "quarterly")
            if isinstance(data.get("rebalance"), dict) else data.get("rebalance_frequency", "quarterly"),
        rebalance_threshold_pct=float(data.get("rebalance", {}).get("threshold_pct", 5.0))
            if isinstance(data.get("rebalance"), dict) else float(data.get("rebalance_threshold_pct", 5.0)),
        stop_loss_pct=data.get("stop_loss_pct"),
        momentum_lookback=int(data.get("momentum_lookback", 252)),
        momentum_top_n=int(data.get("momentum_top_n", 3)),
    )


def _parse_simple_yaml(text: str) -> dict:
    """Minimal YAML parser for simple key-value and nested dict configs."""
    result = {}
    current_key = None
    current_dict = None

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())

        if indent == 0 and ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if val:
                # Try to parse as number
                try:
                    result[key] = float(val)
                    if result[key] == int(result[key]):
                        result[key] = int(result[key])
                except ValueError:
                    result[key] = val
                current_key = None
                current_dict = None
            else:
                current_key = key
                current_dict = {}
                result[key] = current_dict
        elif indent > 0 and current_dict is not None and ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            try:
                current_dict[key] = float(val)
                if current_dict[key] == int(current_dict[key]):
                    current_dict[key] = int(current_dict[key])
            except ValueError:
                current_dict[key] = val

    return result


# ---------------------------------------------------------------------------
# Risk-parity weight computation
# ---------------------------------------------------------------------------

def compute_risk_parity_weights(prices: dict[str, list[float]], lookback: int = 60) -> dict[str, float]:
    """Compute inverse-volatility weights from recent price data."""
    vols = {}
    for ticker, price_list in prices.items():
        if len(price_list) < lookback + 1:
            vols[ticker] = 1.0
            continue
        recent = price_list[-lookback:]
        returns = [(recent[i] / recent[i-1]) - 1 for i in range(1, len(recent))]
        mean_r = sum(returns) / len(returns)
        var = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        vols[ticker] = math.sqrt(var) if var > 0 else 0.001

    inv_vols = {t: 1.0 / v for t, v in vols.items()}
    total = sum(inv_vols.values())
    return {t: v / total for t, v in inv_vols.items()}


# ---------------------------------------------------------------------------
# Run backtest
# ---------------------------------------------------------------------------

def run_backtest(
    config: StrategyConfig,
    period: str = "10y",
    benchmark_ticker: str | None = None,
) -> dict:
    """Run a full backtest and return results dict."""
    # Determine all tickers needed
    all_tickers = list(set(config.tickers + ([benchmark_ticker] if benchmark_ticker else [])))

    # Fetch data
    price_data = fetch_prices(all_tickers, period)
    dates, prices = align_prices(price_data)

    if not dates:
        return {"error": "No price data available for the requested tickers/period"}

    # For risk-parity, compute weights from data
    if config.name == "risk-parity":
        rp_weights = compute_risk_parity_weights(
            {t: prices[t] for t in config.tickers if t in prices}
        )
        config.weights = rp_weights

    # Run main strategy
    daily_returns, portfolio_values, rebalance_count = compute_portfolio_returns(
        dates, prices, config,
    )

    metrics = compute_metrics(
        config.name, config.tickers, config.weights, period,
        dates, daily_returns, portfolio_values, rebalance_count,
    )

    result = {"strategy": asdict(metrics)}

    # Run benchmark if requested
    if benchmark_ticker and benchmark_ticker in prices:
        bench_config = build_strategy("buy-and-hold", [benchmark_ticker])
        bench_returns, bench_values, _ = compute_portfolio_returns(dates, prices, bench_config)
        bench_metrics = compute_metrics(
            f"benchmark ({benchmark_ticker})", [benchmark_ticker],
            {benchmark_ticker: 1.0}, period,
            dates, bench_returns, bench_values, 0,
        )
        result["benchmark"] = asdict(bench_metrics)

        # Alpha and information ratio
        if len(daily_returns) == len(bench_returns) and len(daily_returns) > 1:
            excess = [s - b for s, b in zip(daily_returns, bench_returns)]
            mean_excess = sum(excess) / len(excess)
            var_excess = sum((e - mean_excess) ** 2 for e in excess) / (len(excess) - 1)
            tracking_error = math.sqrt(var_excess) * math.sqrt(TRADING_DAYS_PER_YEAR)
            info_ratio = (mean_excess * TRADING_DAYS_PER_YEAR) / tracking_error if tracking_error > 0 else 0
            result["comparison"] = {
                "alpha_pct": round((metrics.cagr_pct - bench_metrics.cagr_pct), 2),
                "tracking_error_pct": round(tracking_error * 100, 2),
                "information_ratio": round(info_ratio, 3),
                "excess_sharpe": round(metrics.sharpe_ratio - bench_metrics.sharpe_ratio, 3),
            }

    return result


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def print_metrics(metrics: dict, title: str = ""):
    """Pretty-print backtest metrics."""
    m = metrics
    print(f"\n{'='*72}")
    print(f"  BACKTEST: {title or m['strategy']}")
    print(f"{'='*72}")
    print(f"  Period:   {m['start_date']} → {m['end_date']} ({m['years']:.1f} years, {m['trading_days']} days)")
    print(f"  Tickers:  {', '.join(m['tickers'])}")

    # Weights
    w_str = ", ".join(f"{t}: {w*100:.1f}%" for t, w in m['weights'].items() if w > 0)
    print(f"  Weights:  {w_str}")
    print()

    # Returns
    print(f"  ── RETURNS ───────────────────────────────────────────────────")
    print(f"  Total Return:      {m['total_return_pct']:>8.1f}%")
    print(f"  CAGR:              {m['cagr_pct']:>8.2f}%")
    print(f"  Starting Value:    ${m['starting_value']:>10,.2f}")
    print(f"  Ending Value:      ${m['ending_value']:>10,.2f}")
    print()

    # Risk
    print(f"  ── RISK ──────────────────────────────────────────────────────")
    print(f"  Volatility (ann):  {m['annualized_volatility_pct']:>8.2f}%")
    print(f"  Max Drawdown:      {m['max_drawdown_pct']:>8.2f}%")
    print(f"    Start:           {m['max_drawdown_start']}")
    print(f"    End:             {m['max_drawdown_end']}")
    rec = m['max_drawdown_recovery'] or "NOT RECOVERED"
    print(f"    Recovery:        {rec}")
    print()

    # Risk-adjusted
    print(f"  ── RISK-ADJUSTED ─────────────────────────────────────────────")
    print(f"  Sharpe Ratio:      {m['sharpe_ratio']:>8.3f}")
    print(f"  Sortino Ratio:     {m['sortino_ratio']:>8.3f}")
    print(f"  Calmar Ratio:      {m['calmar_ratio']:>8.3f}")
    print()

    # Trading stats
    print(f"  ── TRADING STATS ─────────────────────────────────────────────")
    print(f"  Win Rate:          {m['win_rate_pct']:>8.1f}%")
    print(f"  Avg Daily Return:  {m['avg_daily_return_pct']:>8.4f}%")
    print(f"  Best Day:          {m['best_day_pct']:>8.2f}%")
    print(f"  Worst Day:         {m['worst_day_pct']:>8.2f}%")
    print(f"  Rebalances:        {m['rebalance_count']:>8d}")


def print_comparison(result: dict):
    """Print strategy vs benchmark comparison."""
    if "comparison" not in result:
        return
    c = result["comparison"]
    print(f"\n  ── VS BENCHMARK ──────────────────────────────────────────────")
    print(f"  Alpha:             {c['alpha_pct']:>+8.2f}%")
    print(f"  Tracking Error:    {c['tracking_error_pct']:>8.2f}%")
    print(f"  Information Ratio: {c['information_ratio']:>8.3f}")
    print(f"  Excess Sharpe:     {c['excess_sharpe']:>+8.3f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Strategy backtesting engine — investment-management skill Mode 4",
    )
    parser.add_argument("--strategy", default="buy-and-hold",
                        choices=["buy-and-hold", "equal-weight", "risk-parity",
                                 "momentum", "all-weather", "custom"],
                        help="Built-in strategy preset")
    parser.add_argument("--strategy-file", help="Load strategy from YAML file (autoany artifact)")
    parser.add_argument("--tickers", help="Comma-separated tickers (e.g. SPY,QQQ,BND)")
    parser.add_argument("--period", default="10y", help="Lookback period (e.g. 5y, 10y, 3m)")
    parser.add_argument("--benchmark", help="Benchmark ticker for comparison (e.g. SPY)")
    parser.add_argument("--top", type=int, default=3, help="Top N for momentum strategy")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--egri", action="store_true",
                        help="Output as EGRI Outcome (for autoany evaluator)")
    args = parser.parse_args()

    # Load strategy
    if args.strategy_file:
        config = load_strategy_yaml(args.strategy_file)
    elif args.strategy == "all-weather":
        config = build_strategy("all-weather", [])
    else:
        if not args.tickers:
            print("Error: --tickers required for this strategy", file=sys.stderr)
            raise SystemExit(1)
        tickers = [t.strip().upper() for t in args.tickers.split(",")]
        config = build_strategy(args.strategy, tickers, top=args.top)

    # Run backtest
    result = run_backtest(config, args.period, args.benchmark)

    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        raise SystemExit(1)

    # Output
    if args.egri:
        # EGRI evaluator output — structured Outcome for autoany
        metrics = BacktestMetrics(**result["strategy"])
        outcome = metrics.to_egri_outcome()
        print(json.dumps(outcome, indent=2))
    elif args.json:
        print(json.dumps(result, indent=2))
    else:
        print_metrics(result["strategy"], config.name)
        if "benchmark" in result:
            print_metrics(result["benchmark"])
            print_comparison(result)
        print()

    # Save results
    results_dir = Path.home() / ".investment-management" / "backtests"
    results_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    result_file = results_dir / f"backtest-{config.name}-{ts}.json"
    with open(result_file, "w") as f:
        json.dump(result, f, indent=2)


if __name__ == "__main__":
    main()
