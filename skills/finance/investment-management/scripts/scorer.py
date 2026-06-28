#!/usr/bin/env python3
"""
Investment Scoring (Mode 11) — investment-management skill.

Score securities across 6 dimensions (0-100) through investment philosophy lenses.
Dimensions: Value, Quality, Momentum, Risk, Growth, Income.
Composite score computed as weighted average based on selected philosophy.

Usage:
    python scorer.py --ticker AAPL
    python scorer.py --tickers AAPL,MSFT,JNJ --philosophy value
    python scorer.py --tickers NVDA,AMD --philosophy growth --json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field, asdict
from typing import Any

# ---------------------------------------------------------------------------
# Optional dependency: yfinance
# ---------------------------------------------------------------------------
try:
    import yfinance as yf

    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


# ---------------------------------------------------------------------------
# Philosophy weight profiles
# ---------------------------------------------------------------------------

# Weights for each scoring dimension per philosophy.
# Keys: value, quality, momentum, risk, growth, income
PHILOSOPHY_WEIGHTS: dict[str, dict[str, float]] = {
    "value": {
        "value": 0.35,
        "quality": 0.25,
        "momentum": 0.05,
        "risk": 0.15,
        "growth": 0.10,
        "income": 0.10,
    },
    "growth": {
        "value": 0.05,
        "quality": 0.15,
        "momentum": 0.25,
        "risk": 0.10,
        "growth": 0.35,
        "income": 0.10,
    },
    "balanced": {
        "value": 0.18,
        "quality": 0.20,
        "momentum": 0.15,
        "risk": 0.17,
        "growth": 0.18,
        "income": 0.12,
    },
}


# ---------------------------------------------------------------------------
# Scoring helper: map a raw value into a 0-100 score
# ---------------------------------------------------------------------------

def _score_linear(value: float | None, low: float, high: float, invert: bool = False) -> float | None:
    """
    Map value into 0-100 linearly between [low, high].
    If invert=True, lower raw values score higher (e.g., lower P/E = better value).
    Returns None if value is None.
    """
    if value is None:
        return None
    clamped = max(low, min(high, value))
    normalized = (clamped - low) / (high - low) if high != low else 0.5
    score = (1.0 - normalized) * 100 if invert else normalized * 100
    return round(max(0, min(100, score)), 1)


def _score_threshold(value: float | None, good: float, bad: float) -> float | None:
    """
    Score where being above 'good' = 100, below 'bad' = 0, linear between.
    If good < bad, inverts (lower is better).
    """
    if value is None:
        return None
    if good == bad:
        return 50.0
    if good > bad:
        # Higher is better
        return _score_linear(value, bad, good, invert=False)
    else:
        # Lower is better
        return _score_linear(value, good, bad, invert=True)


def _weighted_avg(scores: list[tuple[float | None, float]]) -> float | None:
    """Weighted average of (score, weight) pairs, skipping None scores."""
    total_weight = 0.0
    total_score = 0.0
    for score, weight in scores:
        if score is not None:
            total_score += score * weight
            total_weight += weight
    if total_weight == 0:
        return None
    return round(total_score / total_weight, 1)


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

@dataclass
class RawData:
    """Raw financial data for a single ticker."""
    ticker: str
    name: str = ""
    sector: str = ""
    price: float | None = None
    market_cap: float | None = None

    # Value metrics
    pe_ratio: float | None = None
    forward_pe: float | None = None
    pb_ratio: float | None = None
    ev_ebitda: float | None = None
    fcf_yield: float | None = None  # percent

    # Quality metrics
    roe: float | None = None  # percent
    roic: float | None = None  # percent (approximated)
    gross_margin: float | None = None  # percent
    operating_margin: float | None = None  # percent
    net_margin: float | None = None  # percent
    debt_equity: float | None = None
    current_ratio: float | None = None
    interest_coverage: float | None = None

    # Momentum metrics
    return_1m: float | None = None  # percent
    return_3m: float | None = None  # percent
    return_6m: float | None = None  # percent
    return_12m: float | None = None  # percent
    eps_growth: float | None = None  # percent
    revenue_growth: float | None = None  # percent

    # Risk metrics
    beta: float | None = None
    volatility_annual: float | None = None  # percent
    max_drawdown: float | None = None  # percent (negative)

    # Growth metrics
    peg_ratio: float | None = None
    revenue_growth_5y: float | None = None  # percent

    # Income metrics
    dividend_yield: float | None = None  # percent
    payout_ratio: float | None = None  # percent
    dividend_growth_5y: float | None = None  # percent

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_pct(raw: float | None, threshold: float = 5.0) -> float | None:
    """Convert yfinance decimal ratios to percentages when they look like decimals."""
    if raw is None:
        return None
    return raw * 100 if abs(raw) < threshold else raw


def _calc_return(hist, months: int) -> float | None:
    """Calculate return over N months from price history dataframe."""
    try:
        trading_days = months * 21
        if hist is None or len(hist) < trading_days:
            return None
        start = hist["Close"].iloc[-trading_days]
        end = hist["Close"].iloc[-1]
        if start and start > 0:
            return ((end - start) / start) * 100
    except Exception:
        pass
    return None


def _calc_volatility(hist) -> float | None:
    """Annualized volatility from daily returns."""
    try:
        if hist is None or len(hist) < 30:
            return None
        prices = hist["Close"]
        if HAS_NUMPY:
            returns = np.diff(np.log(prices.values))
            vol = float(np.std(returns)) * math.sqrt(252) * 100
        else:
            log_returns = []
            vals = list(prices.values)
            for i in range(1, len(vals)):
                if vals[i] > 0 and vals[i - 1] > 0:
                    log_returns.append(math.log(vals[i] / vals[i - 1]))
            if not log_returns:
                return None
            mean_r = sum(log_returns) / len(log_returns)
            var_r = sum((r - mean_r) ** 2 for r in log_returns) / len(log_returns)
            vol = math.sqrt(var_r) * math.sqrt(252) * 100
        return round(vol, 2)
    except Exception:
        return None


def _calc_max_drawdown(hist) -> float | None:
    """Maximum drawdown from price history (returned as negative percentage)."""
    try:
        if hist is None or len(hist) < 30:
            return None
        prices = list(hist["Close"].values)
        peak = prices[0]
        max_dd = 0.0
        for p in prices:
            if p > peak:
                peak = p
            dd = (p - peak) / peak if peak > 0 else 0
            if dd < max_dd:
                max_dd = dd
        return round(max_dd * 100, 2)
    except Exception:
        return None


def fetch_raw_yfinance(ticker_str: str) -> RawData:
    """Fetch comprehensive data for a single ticker via yfinance."""
    t = yf.Ticker(ticker_str)
    info = t.info or {}

    # Get historical data for momentum and risk calculations
    hist_1y = None
    try:
        hist_1y = t.history(period="1y")
    except Exception:
        pass

    # FCF yield
    fcf = info.get("freeCashflow")
    mcap = info.get("marketCap")
    fcf_yield = None
    if fcf and mcap and mcap > 0:
        fcf_yield = (fcf / mcap) * 100

    # Approximate ROIC: EBIT * (1 - tax) / (total equity + total debt)
    roic = None
    try:
        ebit = info.get("ebitda")  # approximate
        total_debt = info.get("totalDebt", 0) or 0
        total_equity = info.get("totalStockholderEquity") or info.get("bookValue", 0)
        if ebit and total_equity and (total_equity + total_debt) > 0:
            roic = (ebit * 0.75) / (total_equity + total_debt) * 100  # ~25% tax assumption
    except Exception:
        pass

    # Debt/equity normalization
    de_raw = info.get("debtToEquity")
    de = None
    if de_raw is not None:
        de = de_raw / 100 if de_raw > 10 else de_raw

    # EV/EBITDA
    ev_ebitda = info.get("enterpriseToEbitda")

    data = RawData(
        ticker=ticker_str,
        name=info.get("shortName", ""),
        sector=info.get("sector", ""),
        price=info.get("currentPrice") or info.get("regularMarketPrice"),
        market_cap=mcap,

        # Value
        pe_ratio=info.get("trailingPE"),
        forward_pe=info.get("forwardPE"),
        pb_ratio=info.get("priceToBook"),
        ev_ebitda=ev_ebitda,
        fcf_yield=fcf_yield,

        # Quality
        roe=_safe_pct(info.get("returnOnEquity")),
        roic=roic,
        gross_margin=_safe_pct(info.get("grossMargins")),
        operating_margin=_safe_pct(info.get("operatingMargins")),
        net_margin=_safe_pct(info.get("profitMargins")),
        debt_equity=de,
        current_ratio=info.get("currentRatio"),

        # Momentum
        return_1m=_calc_return(hist_1y, 1),
        return_3m=_calc_return(hist_1y, 3),
        return_6m=_calc_return(hist_1y, 6),
        return_12m=_calc_return(hist_1y, 12),
        eps_growth=_safe_pct(info.get("earningsGrowth") or info.get("earningsQuarterlyGrowth")),
        revenue_growth=_safe_pct(info.get("revenueGrowth")),

        # Risk
        beta=info.get("beta"),
        volatility_annual=_calc_volatility(hist_1y),
        max_drawdown=_calc_max_drawdown(hist_1y),

        # Growth
        peg_ratio=info.get("pegRatio"),
        revenue_growth_5y=_safe_pct(info.get("revenueGrowth")),  # proxy; 5y not directly available

        # Income
        dividend_yield=_safe_pct(info.get("dividendYield"), threshold=2.0),
        payout_ratio=_safe_pct(info.get("payoutRatio")),
    )

    return data


def fetch_raw_fallback(ticker_str: str) -> RawData:
    """Fallback stub when yfinance is unavailable."""
    print(f"Warning: yfinance not installed. No data for {ticker_str}.", file=sys.stderr)
    print("Install with: pip install yfinance", file=sys.stderr)
    return RawData(ticker=ticker_str)


def fetch_raw(ticker_str: str) -> RawData:
    """Fetch raw data using best available source."""
    if HAS_YFINANCE:
        return fetch_raw_yfinance(ticker_str)
    return fetch_raw_fallback(ticker_str)


# ---------------------------------------------------------------------------
# Dimension scoring
# ---------------------------------------------------------------------------

@dataclass
class DimensionScore:
    """Score breakdown for a single dimension."""
    score: float | None = None
    components: dict[str, float | None] = field(default_factory=dict)
    explanation: str = ""


@dataclass
class Scorecard:
    """Complete scorecard for a security."""
    ticker: str
    name: str = ""
    sector: str = ""
    price: float | None = None
    composite: float | None = None
    philosophy: str = "balanced"
    value: DimensionScore = field(default_factory=DimensionScore)
    quality: DimensionScore = field(default_factory=DimensionScore)
    momentum: DimensionScore = field(default_factory=DimensionScore)
    risk: DimensionScore = field(default_factory=DimensionScore)
    growth: DimensionScore = field(default_factory=DimensionScore)
    income: DimensionScore = field(default_factory=DimensionScore)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "sector": self.sector,
            "price": self.price,
            "composite": self.composite,
            "philosophy": self.philosophy,
            "dimensions": {
                "value": {"score": self.value.score, "components": self.value.components},
                "quality": {"score": self.quality.score, "components": self.quality.components},
                "momentum": {"score": self.momentum.score, "components": self.momentum.components},
                "risk": {"score": self.risk.score, "components": self.risk.components},
                "growth": {"score": self.growth.score, "components": self.growth.components},
                "income": {"score": self.income.score, "components": self.income.components},
            },
        }


def score_value(data: RawData) -> DimensionScore:
    """
    Value dimension: P/E, P/B, FCF yield, EV/EBITDA vs sector norms.
    Lower P/E, P/B, EV/EBITDA = better. Higher FCF yield = better.
    """
    pe_score = _score_threshold(data.pe_ratio, good=10, bad=35)
    fwd_pe_score = _score_threshold(data.forward_pe, good=10, bad=30)
    pb_score = _score_threshold(data.pb_ratio, good=1.0, bad=5.0)
    fcf_score = _score_threshold(data.fcf_yield, good=8, bad=0)
    ev_score = _score_threshold(data.ev_ebitda, good=8, bad=25)

    components = {
        "pe_score": pe_score,
        "forward_pe_score": fwd_pe_score,
        "pb_score": pb_score,
        "fcf_yield_score": fcf_score,
        "ev_ebitda_score": ev_score,
    }

    agg = _weighted_avg([
        (pe_score, 0.25),
        (fwd_pe_score, 0.15),
        (pb_score, 0.20),
        (fcf_score, 0.25),
        (ev_score, 0.15),
    ])

    return DimensionScore(score=agg, components=components)


def score_quality(data: RawData) -> DimensionScore:
    """
    Quality dimension: ROIC, margins, debt discipline.
    Higher ROIC, margins = better. Lower D/E = better.
    """
    roic_score = _score_threshold(data.roic, good=20, bad=5)
    roe_score = _score_threshold(data.roe, good=20, bad=5)
    gm_score = _score_threshold(data.gross_margin, good=50, bad=15)
    om_score = _score_threshold(data.operating_margin, good=25, bad=5)
    nm_score = _score_threshold(data.net_margin, good=15, bad=2)
    de_score = _score_threshold(data.debt_equity, good=0.0, bad=2.0)
    cr_score = _score_threshold(data.current_ratio, good=2.5, bad=0.8)

    components = {
        "roic_score": roic_score,
        "roe_score": roe_score,
        "gross_margin_score": gm_score,
        "operating_margin_score": om_score,
        "net_margin_score": nm_score,
        "debt_equity_score": de_score,
        "current_ratio_score": cr_score,
    }

    agg = _weighted_avg([
        (roic_score, 0.20),
        (roe_score, 0.15),
        (gm_score, 0.15),
        (om_score, 0.15),
        (nm_score, 0.10),
        (de_score, 0.15),
        (cr_score, 0.10),
    ])

    return DimensionScore(score=agg, components=components)


def score_momentum(data: RawData) -> DimensionScore:
    """
    Momentum dimension: price momentum (1/3/6/12m), earnings momentum.
    """
    r1m = _score_threshold(data.return_1m, good=5, bad=-5)
    r3m = _score_threshold(data.return_3m, good=10, bad=-10)
    r6m = _score_threshold(data.return_6m, good=15, bad=-15)
    r12m = _score_threshold(data.return_12m, good=25, bad=-10)
    eps_mom = _score_threshold(data.eps_growth, good=20, bad=-10)
    rev_mom = _score_threshold(data.revenue_growth, good=15, bad=-5)

    components = {
        "return_1m_score": r1m,
        "return_3m_score": r3m,
        "return_6m_score": r6m,
        "return_12m_score": r12m,
        "eps_momentum_score": eps_mom,
        "revenue_momentum_score": rev_mom,
    }

    agg = _weighted_avg([
        (r1m, 0.10),
        (r3m, 0.15),
        (r6m, 0.15),
        (r12m, 0.25),
        (eps_mom, 0.20),
        (rev_mom, 0.15),
    ])

    return DimensionScore(score=agg, components=components)


def score_risk(data: RawData) -> DimensionScore:
    """
    Risk dimension: volatility, max drawdown, beta.
    Lower volatility, smaller drawdowns, beta near 1 = better.
    Risk is scored inversely: lower risk = higher score.
    """
    vol_score = _score_threshold(data.volatility_annual, good=15, bad=50)
    dd_score = _score_threshold(data.max_drawdown, good=-5, bad=-40)
    # Beta: 1.0 is neutral; < 1 is defensive (good for risk), > 1.5 is aggressive
    beta_score = None
    if data.beta is not None:
        # Optimal beta near 0.8-1.0 for risk averse
        if data.beta <= 1.0:
            beta_score = min(100, 50 + (1.0 - data.beta) * 100)
        else:
            beta_score = max(0, 50 - (data.beta - 1.0) * 50)
        beta_score = round(beta_score, 1)

    de_risk = _score_threshold(data.debt_equity, good=0.0, bad=2.0)

    components = {
        "volatility_score": vol_score,
        "max_drawdown_score": dd_score,
        "beta_score": beta_score,
        "leverage_score": de_risk,
    }

    agg = _weighted_avg([
        (vol_score, 0.30),
        (dd_score, 0.30),
        (beta_score, 0.20),
        (de_risk, 0.20),
    ])

    return DimensionScore(score=agg, components=components)


def score_growth(data: RawData) -> DimensionScore:
    """
    Growth dimension: revenue growth, EPS growth, PEG ratio, TAM potential.
    """
    rev_score = _score_threshold(data.revenue_growth, good=20, bad=0)
    eps_score = _score_threshold(data.eps_growth, good=20, bad=0)
    peg_score = _score_threshold(data.peg_ratio, good=0.5, bad=3.0)
    rev5y_score = _score_threshold(data.revenue_growth_5y, good=15, bad=0)

    components = {
        "revenue_growth_score": rev_score,
        "eps_growth_score": eps_score,
        "peg_score": peg_score,
        "revenue_growth_5y_score": rev5y_score,
    }

    agg = _weighted_avg([
        (rev_score, 0.30),
        (eps_score, 0.30),
        (peg_score, 0.25),
        (rev5y_score, 0.15),
    ])

    return DimensionScore(score=agg, components=components)


def score_income(data: RawData) -> DimensionScore:
    """
    Income dimension: dividend yield, payout sustainability.
    Higher yield with lower payout ratio = better.
    """
    yield_score = _score_threshold(data.dividend_yield, good=5, bad=0)
    # Payout: moderate (30-50%) is ideal. Too high (>80%) is unsustainable, too low or 0 is no income.
    payout_score = None
    if data.payout_ratio is not None:
        if data.payout_ratio <= 0:
            payout_score = 0.0
        elif data.payout_ratio <= 60:
            payout_score = min(100, data.payout_ratio * (100 / 60))
        else:
            payout_score = max(0, 100 - (data.payout_ratio - 60) * 2.5)
        payout_score = round(payout_score, 1)

    # Non-payers get a low income score but not necessarily zero across the board
    if data.dividend_yield is not None and data.dividend_yield <= 0:
        yield_score = 0.0
        payout_score = 0.0

    components = {
        "yield_score": yield_score,
        "payout_sustainability_score": payout_score,
    }

    agg = _weighted_avg([
        (yield_score, 0.60),
        (payout_score, 0.40),
    ])

    return DimensionScore(score=agg, components=components)


# ---------------------------------------------------------------------------
# Composite scoring
# ---------------------------------------------------------------------------

def compute_scorecard(data: RawData, philosophy: str = "balanced") -> Scorecard:
    """Compute full scorecard for a security."""
    weights = PHILOSOPHY_WEIGHTS.get(philosophy, PHILOSOPHY_WEIGHTS["balanced"])

    val = score_value(data)
    qual = score_quality(data)
    mom = score_momentum(data)
    rsk = score_risk(data)
    grw = score_growth(data)
    inc = score_income(data)

    composite = _weighted_avg([
        (val.score, weights["value"]),
        (qual.score, weights["quality"]),
        (mom.score, weights["momentum"]),
        (rsk.score, weights["risk"]),
        (grw.score, weights["growth"]),
        (inc.score, weights["income"]),
    ])

    return Scorecard(
        ticker=data.ticker,
        name=data.name,
        sector=data.sector,
        price=data.price,
        composite=composite,
        philosophy=philosophy,
        value=val,
        quality=qual,
        momentum=mom,
        risk=rsk,
        growth=grw,
        income=inc,
    )


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _bar(score: float | None, width: int = 20) -> str:
    """Render a score as a text bar."""
    if score is None:
        return " " * width + "  n/a"
    filled = round(score / 100 * width)
    bar_str = "#" * filled + "." * (width - filled)
    return f"[{bar_str}] {score:5.1f}"


def _grade(score: float | None) -> str:
    """Letter grade for a score."""
    if score is None:
        return "?"
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B+"
    if score >= 60:
        return "B"
    if score >= 50:
        return "C+"
    if score >= 40:
        return "C"
    if score >= 30:
        return "D"
    return "F"


def print_scorecard(card: Scorecard) -> None:
    """Print a human-readable scorecard."""
    name_str = f" ({card.name})" if card.name else ""
    price_str = f"  Price: ${card.price:.2f}" if card.price else ""
    sector_str = f"  Sector: {card.sector}" if card.sector else ""

    print(f"\n{'=' * 60}")
    print(f"  {card.ticker}{name_str}")
    print(f"{sector_str}{price_str}")
    print(f"  Philosophy: {card.philosophy}")
    print(f"{'=' * 60}")

    weights = PHILOSOPHY_WEIGHTS.get(card.philosophy, PHILOSOPHY_WEIGHTS["balanced"])

    dimensions = [
        ("Value", card.value, weights["value"]),
        ("Quality", card.quality, weights["quality"]),
        ("Momentum", card.momentum, weights["momentum"]),
        ("Risk", card.risk, weights["risk"]),
        ("Growth", card.growth, weights["growth"]),
        ("Income", card.income, weights["income"]),
    ]

    print(f"\n  {'Dimension':<12} {'Score':>26}  {'Grade':>5}  {'Weight':>6}")
    print(f"  {'-' * 55}")

    for name, dim, weight in dimensions:
        bar = _bar(dim.score)
        grade = _grade(dim.score)
        wt = f"{weight * 100:.0f}%"
        print(f"  {name:<12} {bar}  {grade:>5}  {wt:>6}")

    print(f"  {'-' * 55}")
    composite_bar = _bar(card.composite)
    composite_grade = _grade(card.composite)
    print(f"  {'COMPOSITE':<12} {composite_bar}  {composite_grade:>5}")
    print()

    # Component details
    print(f"  Component Breakdown:")
    print(f"  {'-' * 55}")
    for name, dim, _ in dimensions:
        if dim.components:
            comps = ", ".join(
                f"{k}={v:.0f}" for k, v in dim.components.items() if v is not None
            )
            if comps:
                print(f"  {name:<12} {comps}")
    print()


def print_comparison_table(cards: list[Scorecard]) -> None:
    """Print a side-by-side comparison table for multiple tickers."""
    if len(cards) == 1:
        print_scorecard(cards[0])
        return

    # Print individual scorecards
    for card in cards:
        print_scorecard(card)

    # Summary comparison table
    print(f"\n{'=' * 70}")
    print(f"  Comparison Summary (philosophy: {cards[0].philosophy})")
    print(f"{'=' * 70}")

    header = f"  {'Ticker':<8} {'Value':>6} {'Qual':>6} {'Mom':>6} {'Risk':>6} {'Grow':>6} {'Inc':>6} {'COMP':>6} {'Grade':>6}"
    print(header)
    print(f"  {'-' * 62}")

    # Sort by composite score descending
    sorted_cards = sorted(cards, key=lambda c: c.composite or 0, reverse=True)
    for card in sorted_cards:
        def f(v: float | None) -> str:
            return f"{v:5.1f}" if v is not None else "  n/a"

        print(
            f"  {card.ticker:<8} "
            f"{f(card.value.score):>6} "
            f"{f(card.quality.score):>6} "
            f"{f(card.momentum.score):>6} "
            f"{f(card.risk.score):>6} "
            f"{f(card.growth.score):>6} "
            f"{f(card.income.score):>6} "
            f"{f(card.composite):>6} "
            f"{_grade(card.composite):>6}"
        )

    print(f"  {'-' * 62}")
    print()


def print_json_output(cards: list[Scorecard]) -> None:
    """Output scorecards as JSON."""
    if len(cards) == 1:
        print(json.dumps(cards[0].to_dict(), indent=2, default=str))
    else:
        output = [c.to_dict() for c in cards]
        print(json.dumps(output, indent=2, default=str))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Investment Scoring (Mode 11) -- investment-management skill",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Philosophy weight profiles:
  value     Heavy on value (35%) and quality (25%)
  growth    Heavy on growth (35%) and momentum (25%)
  balanced  Even spread across all dimensions

Scoring dimensions (0-100 each):
  Value     P/E, P/B, FCF yield, EV/EBITDA vs sector
  Quality   ROIC, margins, debt discipline
  Momentum  Price momentum (1/3/6/12m), earnings momentum
  Risk      Volatility, max drawdown, beta (lower risk = higher score)
  Growth    Revenue growth, EPS growth, PEG ratio
  Income    Dividend yield, payout sustainability

Examples:
  python scorer.py --ticker AAPL
  python scorer.py --tickers AAPL,MSFT,JNJ --philosophy value
  python scorer.py --tickers NVDA,AMD --philosophy growth --json
        """,
    )

    ticker_group = p.add_mutually_exclusive_group(required=True)
    ticker_group.add_argument("--ticker", type=str, help="Single ticker to score")
    ticker_group.add_argument("--tickers", type=str, help="Comma-separated tickers to score")

    p.add_argument("--philosophy", choices=["value", "growth", "balanced"],
                    default="balanced", help="Philosophy lens for composite weighting (default: balanced)")

    p.add_argument("--json", action="store_true", help="Output as JSON")

    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    # Parse tickers
    if args.ticker:
        tickers = [args.ticker.upper()]
    else:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]

    if not tickers:
        print("Error: no tickers provided.", file=sys.stderr)
        sys.exit(1)

    philosophy = args.philosophy
    print(f"Scoring {len(tickers)} ticker(s) with '{philosophy}' philosophy...", file=sys.stderr)

    # Fetch and score
    cards: list[Scorecard] = []
    for idx, ticker_str in enumerate(tickers, 1):
        print(f"  [{idx}/{len(tickers)}] {ticker_str}...", file=sys.stderr)
        try:
            data = fetch_raw(ticker_str)
            card = compute_scorecard(data, philosophy)
            cards.append(card)
        except Exception as e:
            print(f"  Error scoring {ticker_str}: {e}", file=sys.stderr)
            cards.append(Scorecard(ticker=ticker_str, philosophy=philosophy))

    # Output
    if args.json:
        print_json_output(cards)
    else:
        print_comparison_table(cards)


if __name__ == "__main__":
    main()
