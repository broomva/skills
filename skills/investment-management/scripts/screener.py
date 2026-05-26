#!/usr/bin/env python3
"""
Security Screening (Mode 1) — investment-management skill.

Search and filter stocks/ETFs by fundamental, quality, momentum, and value criteria.
Pre-built philosophy screens: value, quality, growth, dividend, momentum.

Usage:
    python screener.py --philosophy value --universe sp500 --limit 20
    python screener.py --min-pe 5 --max-pe 15 --min-roe 15 --json
    python screener.py --philosophy dividend --universe custom --tickers AAPL,MSFT,JNJ
"""

from __future__ import annotations

import argparse
import json
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
    import pandas as pd

    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


# ---------------------------------------------------------------------------
# Stock universes
# ---------------------------------------------------------------------------

# Representative subsets — full lists would be fetched from an index provider.
# These are trimmed to keep the script self-contained.
SP500_SAMPLE: list[str] = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "BRK-B", "UNH", "XOM",
    "JNJ", "JPM", "V", "PG", "MA", "HD", "CVX", "MRK", "ABBV", "LLY", "PEP",
    "KO", "COST", "AVGO", "WMT", "MCD", "CSCO", "CRM", "ACN", "TMO", "ABT",
    "DHR", "LIN", "NEE", "PM", "TXN", "UNP", "RTX", "LOW", "HON", "IBM",
    "AMGN", "CAT", "SPGI", "GE", "BA", "BLK", "MDLZ", "PLD", "GILD", "MMM",
    "CI", "CB", "ADI", "SYK", "MO", "ZTS", "CME", "DUK", "SO", "CL",
    "BDX", "REGN", "ITW", "PNC", "TGT", "APD", "ECL", "SHW", "WM", "ADP",
    "NOC", "GD", "MMC", "AIG", "TRV", "PSA", "SPG", "O", "AFL", "MET",
    "ALL", "D", "SRE", "AEP", "XEL", "WEC", "ES", "ED", "EXC", "PEG",
    "KMB", "GIS", "K", "SJM", "CAG", "HRL", "CPB", "MKC", "CLX", "CHD",
]

NASDAQ100_SAMPLE: list[str] = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "AVGO", "COST", "TSLA",
    "NFLX", "AMD", "ADBE", "PEP", "CSCO", "INTC", "CMCSA", "TMUS", "TXN",
    "QCOM", "INTU", "AMGN", "ISRG", "AMAT", "BKNG", "LRCX", "ADI", "MU",
    "GILD", "MDLZ", "ADP", "REGN", "SNPS", "KLAC", "CDNS", "PANW", "MELI",
    "MAR", "PYPL", "MNST", "ORLY", "FTNT", "CTAS", "KDP", "ABNB", "NXPI",
    "MCHP", "AEP", "PCAR", "DXCM", "LULU",
]


def get_universe(name: str, custom_tickers: list[str] | None = None) -> list[str]:
    """Return list of tickers for the requested universe."""
    if name == "sp500":
        return SP500_SAMPLE
    elif name == "nasdaq100":
        return NASDAQ100_SAMPLE
    elif name == "custom":
        if not custom_tickers:
            print("Error: --universe custom requires --tickers", file=sys.stderr)
            sys.exit(1)
        return custom_tickers
    else:
        print(f"Error: unknown universe '{name}'", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Pre-built philosophy screens
# ---------------------------------------------------------------------------

@dataclass
class ScreenCriteria:
    """Defines filter thresholds for screening."""
    min_pe: float | None = None
    max_pe: float | None = None
    min_pb: float | None = None
    max_pb: float | None = None
    min_roe: float | None = None  # percent
    max_debt_equity: float | None = None
    min_revenue_growth: float | None = None  # percent
    min_current_ratio: float | None = None
    max_peg: float | None = None
    min_eps_growth: float | None = None  # percent
    min_dividend_yield: float | None = None  # percent
    max_payout_ratio: float | None = None  # percent
    min_12m_return: float | None = None  # percent
    min_fcf_yield: float | None = None  # percent
    sort_by: str = "composite"
    sort_ascending: bool = True


PHILOSOPHY_SCREENS: dict[str, ScreenCriteria] = {
    "value": ScreenCriteria(
        min_pe=0.1, max_pe=15.0,
        max_pb=1.5,
        min_current_ratio=2.0,
        sort_by="pe_ratio", sort_ascending=True,
    ),
    "quality": ScreenCriteria(
        min_roe=15.0,
        max_debt_equity=0.5,
        min_revenue_growth=5.0,
        sort_by="roe", sort_ascending=False,
    ),
    "growth": ScreenCriteria(
        max_peg=1.0,
        min_revenue_growth=15.0,
        min_eps_growth=0.0,
        sort_by="revenue_growth", sort_ascending=False,
    ),
    "dividend": ScreenCriteria(
        min_dividend_yield=3.0,
        max_payout_ratio=60.0,
        sort_by="dividend_yield", sort_ascending=False,
    ),
    "momentum": ScreenCriteria(
        min_12m_return=20.0,
        sort_by="return_12m", sort_ascending=False,
    ),
}


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

@dataclass
class SecurityMetrics:
    """Collected metrics for a single security."""
    ticker: str
    name: str = ""
    sector: str = ""
    market_cap: float | None = None
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    peg_ratio: float | None = None
    roe: float | None = None  # percent
    debt_equity: float | None = None
    revenue_growth: float | None = None  # percent
    eps_growth: float | None = None  # percent
    current_ratio: float | None = None
    dividend_yield: float | None = None  # percent
    payout_ratio: float | None = None  # percent
    fcf_yield: float | None = None  # percent
    return_12m: float | None = None  # percent
    price: float | None = None
    _pass: bool = True  # whether it passed the screen

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("_pass", None)
        return d


def fetch_metrics_yfinance(tickers: list[str], progress: bool = True) -> list[SecurityMetrics]:
    """Fetch metrics using yfinance. Returns list of SecurityMetrics."""
    results: list[SecurityMetrics] = []
    total = len(tickers)

    for idx, ticker_str in enumerate(tickers, 1):
        if progress and not sys.stdout.isatty():
            pass  # skip progress for piped output
        elif progress:
            print(f"\r  Fetching {idx}/{total}: {ticker_str:<6}", end="", flush=True, file=sys.stderr)

        try:
            t = yf.Ticker(ticker_str)
            info = t.info or {}

            # Calculate 12-month return from history
            return_12m = None
            try:
                hist = t.history(period="1y")
                if hist is not None and len(hist) >= 2:
                    start_price = hist["Close"].iloc[0]
                    end_price = hist["Close"].iloc[-1]
                    if start_price and start_price > 0:
                        return_12m = ((end_price - start_price) / start_price) * 100
            except Exception:
                pass

            # FCF yield: free cash flow / market cap
            fcf_yield = None
            fcf = info.get("freeCashflow")
            mcap = info.get("marketCap")
            if fcf and mcap and mcap > 0:
                fcf_yield = (fcf / mcap) * 100

            # ROE: sometimes given as decimal, sometimes percent
            roe_raw = info.get("returnOnEquity")
            roe = None
            if roe_raw is not None:
                roe = roe_raw * 100 if abs(roe_raw) < 5 else roe_raw

            # Revenue growth
            rev_growth_raw = info.get("revenueGrowth")
            rev_growth = None
            if rev_growth_raw is not None:
                rev_growth = rev_growth_raw * 100 if abs(rev_growth_raw) < 5 else rev_growth_raw

            # EPS growth (earnings growth)
            eps_growth_raw = info.get("earningsGrowth") or info.get("earningsQuarterlyGrowth")
            eps_growth = None
            if eps_growth_raw is not None:
                eps_growth = eps_growth_raw * 100 if abs(eps_growth_raw) < 5 else eps_growth_raw

            # Dividend yield
            div_yield_raw = info.get("dividendYield")
            div_yield = None
            if div_yield_raw is not None:
                div_yield = div_yield_raw * 100 if abs(div_yield_raw) < 2 else div_yield_raw

            # Payout ratio
            payout_raw = info.get("payoutRatio")
            payout = None
            if payout_raw is not None:
                payout = payout_raw * 100 if abs(payout_raw) < 5 else payout_raw

            # Debt/equity
            de_raw = info.get("debtToEquity")
            de = None
            if de_raw is not None:
                # yfinance sometimes returns as percent (e.g., 50 meaning 0.5)
                de = de_raw / 100 if de_raw > 10 else de_raw

            m = SecurityMetrics(
                ticker=ticker_str,
                name=info.get("shortName", ""),
                sector=info.get("sector", ""),
                market_cap=mcap,
                pe_ratio=info.get("trailingPE") or info.get("forwardPE"),
                pb_ratio=info.get("priceToBook"),
                peg_ratio=info.get("pegRatio"),
                roe=roe,
                debt_equity=de,
                revenue_growth=rev_growth,
                eps_growth=eps_growth,
                current_ratio=info.get("currentRatio"),
                dividend_yield=div_yield,
                payout_ratio=payout,
                fcf_yield=fcf_yield,
                return_12m=return_12m,
                price=info.get("currentPrice") or info.get("regularMarketPrice"),
            )
            results.append(m)

        except Exception as e:
            print(f"\n  Warning: failed to fetch {ticker_str}: {e}", file=sys.stderr)
            results.append(SecurityMetrics(ticker=ticker_str, _pass=False))

    if progress:
        print("", file=sys.stderr)  # newline after progress

    return results


def fetch_metrics_fallback(tickers: list[str]) -> list[SecurityMetrics]:
    """Fallback when yfinance is not available. Returns stub data."""
    print("Warning: yfinance not installed. Using empty stub data.", file=sys.stderr)
    print("Install with: pip install yfinance", file=sys.stderr)
    return [SecurityMetrics(ticker=t) for t in tickers]


def fetch_metrics(tickers: list[str]) -> list[SecurityMetrics]:
    """Fetch security metrics using best available source."""
    if HAS_YFINANCE:
        return fetch_metrics_yfinance(tickers)
    return fetch_metrics_fallback(tickers)


# ---------------------------------------------------------------------------
# Screening logic
# ---------------------------------------------------------------------------

def _check(value: float | None, minimum: float | None, maximum: float | None) -> bool:
    """Return True if value passes the min/max filter (None = no filter)."""
    if value is None:
        return True  # missing data does not disqualify
    if minimum is not None and value < minimum:
        return False
    if maximum is not None and value > maximum:
        return False
    return True


def apply_screen(metrics: list[SecurityMetrics], criteria: ScreenCriteria) -> list[SecurityMetrics]:
    """Filter metrics by screen criteria. Returns passing securities."""
    passed: list[SecurityMetrics] = []

    for m in metrics:
        if not _check(m.pe_ratio, criteria.min_pe, criteria.max_pe):
            continue
        if not _check(m.pb_ratio, criteria.min_pb, criteria.max_pb):
            continue
        if not _check(m.roe, criteria.min_roe, None):
            continue
        if not _check(m.debt_equity, None, criteria.max_debt_equity):
            continue
        if not _check(m.revenue_growth, criteria.min_revenue_growth, None):
            continue
        if not _check(m.current_ratio, criteria.min_current_ratio, None):
            continue
        if not _check(m.peg_ratio, None, criteria.max_peg):
            continue
        if not _check(m.eps_growth, criteria.min_eps_growth, None):
            continue
        if not _check(m.dividend_yield, criteria.min_dividend_yield, None):
            continue
        if not _check(m.payout_ratio, None, criteria.max_payout_ratio):
            continue
        if not _check(m.return_12m, criteria.min_12m_return, None):
            continue
        if not _check(m.fcf_yield, criteria.min_fcf_yield, None):
            continue

        m._pass = True
        passed.append(m)

    # Sort
    sort_key = criteria.sort_by
    def sort_val(s: SecurityMetrics) -> float:
        v = getattr(s, sort_key, None)
        if v is None:
            return float("inf") if criteria.sort_ascending else float("-inf")
        return v

    passed.sort(key=sort_val, reverse=not criteria.sort_ascending)
    return passed


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _fmt(val: Any, suffix: str = "", decimals: int = 2) -> str:
    """Format a value for table display."""
    if val is None:
        return "-"
    if isinstance(val, float):
        return f"{val:.{decimals}f}{suffix}"
    return str(val)


def _fmt_mcap(val: float | None) -> str:
    """Format market cap in human-readable form."""
    if val is None:
        return "-"
    if val >= 1e12:
        return f"${val / 1e12:.1f}T"
    if val >= 1e9:
        return f"${val / 1e9:.1f}B"
    if val >= 1e6:
        return f"${val / 1e6:.0f}M"
    return f"${val:,.0f}"


def print_table(results: list[SecurityMetrics], limit: int | None = None) -> None:
    """Print a formatted table of screening results."""
    if limit:
        results = results[:limit]

    if not results:
        print("No securities passed the screen.")
        return

    # Header
    header = (
        f"{'#':>3}  {'Ticker':<7} {'Name':<25} {'Sector':<18} "
        f"{'Price':>8} {'MktCap':>9} {'P/E':>7} {'P/B':>6} "
        f"{'ROE%':>6} {'D/E':>6} {'DivY%':>6} {'FCF%':>6} {'12mR%':>7}"
    )
    separator = "-" * len(header)

    print(f"\nScreening Results ({len(results)} securities)\n")
    print(header)
    print(separator)

    for idx, m in enumerate(results, 1):
        name = (m.name[:24] if m.name else "")
        sector = (m.sector[:17] if m.sector else "")
        row = (
            f"{idx:>3}  {m.ticker:<7} {name:<25} {sector:<18} "
            f"{_fmt(m.price, '$'):>8} {_fmt_mcap(m.market_cap):>9} "
            f"{_fmt(m.pe_ratio):>7} {_fmt(m.pb_ratio):>6} "
            f"{_fmt(m.roe, '%'):>6} {_fmt(m.debt_equity):>6} "
            f"{_fmt(m.dividend_yield, '%'):>6} {_fmt(m.fcf_yield, '%'):>6} "
            f"{_fmt(m.return_12m, '%', 1):>7}"
        )
        print(row)

    print(separator)
    print(f"Total: {len(results)} securities")


def print_json(results: list[SecurityMetrics], limit: int | None = None) -> None:
    """Output results as JSON."""
    if limit:
        results = results[:limit]
    output = [m.to_dict() for m in results]
    print(json.dumps(output, indent=2, default=str))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_criteria_from_args(args: argparse.Namespace) -> ScreenCriteria:
    """Build ScreenCriteria from CLI args, merging philosophy defaults with overrides."""
    # Start from philosophy preset if given
    if args.philosophy and args.philosophy in PHILOSOPHY_SCREENS:
        criteria = PHILOSOPHY_SCREENS[args.philosophy]
        # Create a copy so we don't mutate the preset
        criteria = ScreenCriteria(**asdict(criteria))
    else:
        criteria = ScreenCriteria()

    # CLI args override philosophy defaults
    if args.min_pe is not None:
        criteria.min_pe = args.min_pe
    if args.max_pe is not None:
        criteria.max_pe = args.max_pe
    if args.min_pb is not None:
        criteria.min_pb = args.min_pb
    if args.max_pb is not None:
        criteria.max_pb = args.max_pb
    if args.min_roe is not None:
        criteria.min_roe = args.min_roe
    if args.max_debt_equity is not None:
        criteria.max_debt_equity = args.max_debt_equity
    if args.min_revenue_growth is not None:
        criteria.min_revenue_growth = args.min_revenue_growth
    if args.min_current_ratio is not None:
        criteria.min_current_ratio = args.min_current_ratio
    if args.max_peg is not None:
        criteria.max_peg = args.max_peg
    if args.min_eps_growth is not None:
        criteria.min_eps_growth = args.min_eps_growth
    if args.min_dividend_yield is not None:
        criteria.min_dividend_yield = args.min_dividend_yield
    if args.max_payout_ratio is not None:
        criteria.max_payout_ratio = args.max_payout_ratio
    if args.min_12m_return is not None:
        criteria.min_12m_return = args.min_12m_return
    if args.min_fcf_yield is not None:
        criteria.min_fcf_yield = args.min_fcf_yield
    if args.sort_by:
        criteria.sort_by = args.sort_by
    if args.sort_desc:
        criteria.sort_ascending = False

    return criteria


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Security Screening (Mode 1) -- investment-management skill",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Pre-built philosophy screens:
  value      Graham: P/E < 15, P/B < 1.5, current ratio > 2
  quality    Buffett/Munger: ROE > 15%, D/E < 0.5, rev growth > 5%
  growth     Lynch: PEG < 1, rev growth > 15%, positive EPS growth
  dividend   Income: yield > 3%, payout ratio < 60%
  momentum   12-month return > 20%

Examples:
  python screener.py --philosophy value --universe sp500
  python screener.py --min-pe 5 --max-pe 15 --min-roe 15 --limit 10
  python screener.py --philosophy dividend --universe custom --tickers JNJ,PG,KO,MCD
        """,
    )

    # Universe
    p.add_argument("--universe", choices=["sp500", "nasdaq100", "custom"], default="sp500",
                    help="Stock universe to screen (default: sp500)")
    p.add_argument("--tickers", type=str, default=None,
                    help="Comma-separated tickers for --universe custom")

    # Philosophy
    p.add_argument("--philosophy", choices=["value", "quality", "growth", "dividend", "momentum"],
                    default=None, help="Pre-built philosophy screen")

    # Fundamental filters
    p.add_argument("--min-pe", type=float, default=None, help="Minimum P/E ratio")
    p.add_argument("--max-pe", type=float, default=None, help="Maximum P/E ratio")
    p.add_argument("--min-pb", type=float, default=None, help="Minimum P/B ratio")
    p.add_argument("--max-pb", type=float, default=None, help="Maximum P/B ratio")
    p.add_argument("--min-roe", type=float, default=None, help="Minimum ROE (%%)")
    p.add_argument("--max-debt-equity", type=float, default=None, help="Maximum debt/equity ratio")
    p.add_argument("--min-revenue-growth", type=float, default=None, help="Minimum revenue growth (%%)")
    p.add_argument("--min-current-ratio", type=float, default=None, help="Minimum current ratio")
    p.add_argument("--max-peg", type=float, default=None, help="Maximum PEG ratio")
    p.add_argument("--min-eps-growth", type=float, default=None, help="Minimum EPS growth (%%)")
    p.add_argument("--min-dividend-yield", type=float, default=None, help="Minimum dividend yield (%%)")
    p.add_argument("--max-payout-ratio", type=float, default=None, help="Maximum payout ratio (%%)")
    p.add_argument("--min-12m-return", type=float, default=None, help="Minimum 12-month return (%%)")
    p.add_argument("--min-fcf-yield", type=float, default=None, help="Minimum free cash flow yield (%%)")

    # Sorting
    p.add_argument("--sort-by", type=str, default=None,
                    help="Sort results by metric (pe_ratio, roe, dividend_yield, return_12m, etc.)")
    p.add_argument("--sort-desc", action="store_true", help="Sort descending")

    # Output
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.add_argument("--limit", type=int, default=None, help="Limit number of results")

    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    # Build criteria
    criteria = build_criteria_from_args(args)

    # Describe active screen
    screen_desc = args.philosophy or "custom"
    print(f"Screen: {screen_desc}", file=sys.stderr)

    # Get universe
    custom_tickers = args.tickers.split(",") if args.tickers else None
    tickers = get_universe(args.universe, custom_tickers)
    print(f"Universe: {args.universe} ({len(tickers)} securities)", file=sys.stderr)

    # Fetch data
    print("Fetching data...", file=sys.stderr)
    metrics = fetch_metrics(tickers)

    # Apply screen
    results = apply_screen(metrics, criteria)
    print(f"Passed: {len(results)} / {len(metrics)}", file=sys.stderr)

    # Output
    if args.json:
        print_json(results, args.limit)
    else:
        print_table(results, args.limit)


if __name__ == "__main__":
    main()
