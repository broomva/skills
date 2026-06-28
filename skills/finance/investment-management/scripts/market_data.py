#!/usr/bin/env python3
"""
Unified market data retrieval from multiple free sources.

Mode 10 (data) of the investment-management skill.
Fetches stock prices, fundamentals, crypto, macro series, and Colombian TRM
with graceful fallbacks when optional libraries are not installed.

Usage:
    python3 market_data.py --ticker AAPL --type price
    python3 market_data.py --tickers AAPL,MSFT,GOOG --type price --period 1y
    python3 market_data.py --ticker AAPL --type fundamentals
    python3 market_data.py --ticker AAPL --type profile
    python3 market_data.py --ticker AAPL --type dividends
    python3 market_data.py --crypto BTC --type crypto
    python3 market_data.py --crypto BTC,ETH,SOL --type crypto
    python3 market_data.py --macro GDP,CPI,UNRATE --type macro
    python3 market_data.py --trm
    python3 market_data.py --trm --period 30d
    python3 market_data.py --ticker AAPL --type price --json
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Optional library imports — graceful degradation
# ---------------------------------------------------------------------------

_yfinance = None
_pycoingecko = None
_fredapi = None

try:
    import yfinance as _yfinance
except ImportError:
    pass

try:
    from pycoingecko import CoinGeckoAPI as _CoinGeckoAPI
except ImportError:
    _CoinGeckoAPI = None

try:
    from fredapi import Fred as _FredClass
except ImportError:
    _FredClass = None


DATA_DIR = Path.home() / ".investment-management"
CACHE_DIR = DATA_DIR / "market-data"

# CoinGecko top-coin ID mapping (extend as needed)
CRYPTO_ID_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "ADA": "cardano",
    "DOT": "polkadot",
    "AVAX": "avalanche-2",
    "MATIC": "matic-network",
    "LINK": "chainlink",
    "UNI": "uniswap",
    "ATOM": "cosmos",
    "NEAR": "near",
    "XRP": "ripple",
    "DOGE": "dogecoin",
    "SHIB": "shiba-inu",
    "LTC": "litecoin",
    "BNB": "binancecoin",
    "ARB": "arbitrum",
    "OP": "optimism",
    "APT": "aptos",
    "SUI": "sui",
}

PERIOD_DAYS = {
    "1d": 1,
    "5d": 5,
    "1m": 30,
    "3m": 90,
    "6m": 180,
    "1y": 365,
    "2y": 730,
    "5y": 1825,
    "10y": 3650,
    "max": 10000,
}

# TRM API (same as finance-substrate)
TRM_API = "https://www.datos.gov.co/resource/32sa-8pi3.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ensure_dirs():
    for sub in ["prices", "fundamentals"]:
        (CACHE_DIR / sub).mkdir(parents=True, exist_ok=True)


def _require_yfinance():
    if _yfinance is None:
        print("Error: yfinance is required for stock data.", file=sys.stderr)
        print("  Install: pip install yfinance", file=sys.stderr)
        sys.exit(1)


def _require_coingecko():
    if _CoinGeckoAPI is None:
        print("Error: pycoingecko is required for crypto data.", file=sys.stderr)
        print("  Install: pip install pycoingecko", file=sys.stderr)
        sys.exit(1)


def _require_fred():
    if _FredClass is None:
        print("Error: fredapi is required for macro data.", file=sys.stderr)
        print("  Install: pip install fredapi", file=sys.stderr)
        sys.exit(1)
    api_key = _get_fred_key()
    if not api_key:
        print("Error: FRED API key not found.", file=sys.stderr)
        print("  Set FRED_API_KEY env var or add to ~/.finance-substrate/config.json", file=sys.stderr)
        print("  Get a free key at: https://fred.stlouisfed.org/docs/api/api_key.html", file=sys.stderr)
        sys.exit(1)


def _get_fred_key() -> str | None:
    import os
    key = os.environ.get("FRED_API_KEY")
    if key:
        return key
    config_file = Path.home() / ".finance-substrate" / "config.json"
    if config_file.exists():
        with open(config_file) as f:
            cfg = json.load(f)
            return cfg.get("fred_api_key")
    config_file2 = DATA_DIR / "config" / "config.json"
    if config_file2.exists():
        with open(config_file2) as f:
            cfg = json.load(f)
            return cfg.get("fred_api_key")
    return None


def _period_to_days(period: str) -> int:
    if period.endswith("d") and period[:-1].isdigit():
        return int(period[:-1])
    return PERIOD_DAYS.get(period, 365)


def _fmt_number(val, decimals=2) -> str:
    """Format a number with commas and fixed decimals."""
    if val is None:
        return "N/A"
    if isinstance(val, (int, float)):
        if abs(val) >= 1e9:
            return f"${val / 1e9:,.{decimals}f}B"
        if abs(val) >= 1e6:
            return f"${val / 1e6:,.{decimals}f}M"
        return f"{val:,.{decimals}f}"
    return str(val)


def _print_table(headers: list, rows: list, col_widths: list | None = None):
    """Print a formatted table to stdout."""
    if not rows:
        print("  (no data)")
        return
    if col_widths is None:
        col_widths = []
        for i, h in enumerate(headers):
            w = len(str(h))
            for row in rows:
                if i < len(row):
                    w = max(w, len(str(row[i])))
            col_widths.append(w + 2)

    header_line = "".join(str(h).ljust(col_widths[i]) for i, h in enumerate(headers))
    print(f"  {header_line}")
    print(f"  {'─' * sum(col_widths)}")
    for row in rows:
        line = "".join(str(row[i] if i < len(row) else "").ljust(col_widths[i]) for i in range(len(headers)))
        print(f"  {line}")


# ---------------------------------------------------------------------------
# Data fetchers
# ---------------------------------------------------------------------------

def fetch_stock_prices(tickers: list[str], period: str) -> dict:
    """Fetch historical prices via yfinance."""
    _require_yfinance()
    results = {}
    for ticker in tickers:
        try:
            t = _yfinance.Ticker(ticker)
            hist = t.history(period=period)
            if hist.empty:
                print(f"  Warning: no price data for {ticker}", file=sys.stderr)
                continue
            records = []
            for date_idx, row in hist.iterrows():
                records.append({
                    "date": date_idx.strftime("%Y-%m-%d"),
                    "open": round(row["Open"], 2),
                    "high": round(row["High"], 2),
                    "low": round(row["Low"], 2),
                    "close": round(row["Close"], 2),
                    "volume": int(row["Volume"]),
                })
            results[ticker] = records
        except Exception as e:
            print(f"  Error fetching {ticker}: {e}", file=sys.stderr)
    return results


def fetch_fundamentals(tickers: list[str]) -> dict:
    """Fetch fundamental data via yfinance."""
    _require_yfinance()
    results = {}
    for ticker in tickers:
        try:
            t = _yfinance.Ticker(ticker)
            info = t.info or {}
            results[ticker] = {
                "market_cap": info.get("marketCap"),
                "pe_trailing": info.get("trailingPE"),
                "pe_forward": info.get("forwardPE"),
                "pb_ratio": info.get("priceToBook"),
                "ps_ratio": info.get("priceToSalesTrailing12Months"),
                "ev_ebitda": info.get("enterpriseToEbitda"),
                "roe": info.get("returnOnEquity"),
                "roa": info.get("returnOnAssets"),
                "profit_margin": info.get("profitMargins"),
                "operating_margin": info.get("operatingMargins"),
                "revenue": info.get("totalRevenue"),
                "net_income": info.get("netIncomeToCommon"),
                "free_cash_flow": info.get("freeCashflow"),
                "debt_to_equity": info.get("debtToEquity"),
                "current_ratio": info.get("currentRatio"),
                "beta": info.get("beta"),
                "dividend_yield": info.get("dividendYield"),
                "payout_ratio": info.get("payoutRatio"),
                "earnings_growth": info.get("earningsGrowth"),
                "revenue_growth": info.get("revenueGrowth"),
            }
        except Exception as e:
            print(f"  Error fetching fundamentals for {ticker}: {e}", file=sys.stderr)
    return results


def fetch_profile(tickers: list[str]) -> dict:
    """Fetch company profile via yfinance."""
    _require_yfinance()
    results = {}
    for ticker in tickers:
        try:
            t = _yfinance.Ticker(ticker)
            info = t.info or {}
            results[ticker] = {
                "name": info.get("longName") or info.get("shortName"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "country": info.get("country"),
                "employees": info.get("fullTimeEmployees"),
                "website": info.get("website"),
                "exchange": info.get("exchange"),
                "currency": info.get("currency"),
                "market_cap": info.get("marketCap"),
                "52w_high": info.get("fiftyTwoWeekHigh"),
                "52w_low": info.get("fiftyTwoWeekLow"),
                "avg_volume": info.get("averageVolume"),
                "summary": info.get("longBusinessSummary", "")[:300],
            }
        except Exception as e:
            print(f"  Error fetching profile for {ticker}: {e}", file=sys.stderr)
    return results


def fetch_dividends(tickers: list[str]) -> dict:
    """Fetch dividend history via yfinance."""
    _require_yfinance()
    results = {}
    for ticker in tickers:
        try:
            t = _yfinance.Ticker(ticker)
            divs = t.dividends
            if divs is None or divs.empty:
                results[ticker] = []
                continue
            records = []
            for date_idx, val in divs.items():
                records.append({
                    "date": date_idx.strftime("%Y-%m-%d"),
                    "dividend": round(float(val), 4),
                })
            results[ticker] = records
        except Exception as e:
            print(f"  Error fetching dividends for {ticker}: {e}", file=sys.stderr)
    return results


def fetch_crypto(symbols: list[str], period: str) -> dict:
    """Fetch crypto data via CoinGecko."""
    _require_coingecko()
    cg = _CoinGeckoAPI()
    days = _period_to_days(period)
    results = {}

    for symbol in symbols:
        sym_upper = symbol.upper()
        coin_id = CRYPTO_ID_MAP.get(sym_upper)
        if not coin_id:
            # Attempt to use symbol as coin_id directly
            coin_id = symbol.lower()

        try:
            # Current price + market data
            data = cg.get_coin_by_id(
                coin_id,
                localization=False,
                tickers=False,
                community_data=False,
                developer_data=False,
            )
            market = data.get("market_data", {})
            current = {
                "name": data.get("name"),
                "symbol": data.get("symbol", "").upper(),
                "price_usd": market.get("current_price", {}).get("usd"),
                "market_cap": market.get("market_cap", {}).get("usd"),
                "volume_24h": market.get("total_volume", {}).get("usd"),
                "change_24h_pct": market.get("price_change_percentage_24h"),
                "change_7d_pct": market.get("price_change_percentage_7d"),
                "change_30d_pct": market.get("price_change_percentage_30d"),
                "ath": market.get("ath", {}).get("usd"),
                "ath_date": market.get("ath_date", {}).get("usd", "")[:10],
                "circulating_supply": market.get("circulating_supply"),
                "max_supply": market.get("max_supply"),
            }

            # Historical prices
            history = cg.get_coin_market_chart_by_id(
                coin_id, vs_currency="usd", days=days
            )
            prices = []
            for ts, price in history.get("prices", []):
                prices.append({
                    "date": datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d"),
                    "price": round(price, 2),
                })

            results[sym_upper] = {
                "current": current,
                "history": prices,
            }
        except Exception as e:
            print(f"  Error fetching crypto {sym_upper}: {e}", file=sys.stderr)

    return results


def fetch_macro(series_ids: list[str], period: str) -> dict:
    """Fetch macro data from FRED."""
    _require_fred()
    fred = _FredClass(api_key=_get_fred_key())
    days = _period_to_days(period)
    start = datetime.now() - timedelta(days=days)
    results = {}

    for sid in series_ids:
        try:
            info = fred.get_series_info(sid)
            data = fred.get_series(sid, observation_start=start)
            records = []
            for date_idx, val in data.items():
                if val is not None and str(val) != "nan":
                    records.append({
                        "date": date_idx.strftime("%Y-%m-%d"),
                        "value": round(float(val), 4),
                    })
            results[sid] = {
                "title": str(info.get("title", sid)),
                "units": str(info.get("units", "")),
                "frequency": str(info.get("frequency", "")),
                "data": records,
            }
        except Exception as e:
            print(f"  Error fetching FRED series {sid}: {e}", file=sys.stderr)

    return results


def fetch_trm(period: str) -> list:
    """Fetch TRM (USD/COP) from datos.gov.co."""
    days = _period_to_days(period)
    d_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    d_to = datetime.now().strftime("%Y-%m-%d")

    params = {
        "$order": "vigenciadesde DESC",
        "$limit": "1000",
        "$where": (
            f"vigenciadesde >= '{d_from}T00:00:00.000' "
            f"AND vigenciadesde <= '{d_to}T23:59:59.999'"
        ),
    }

    url = f"{TRM_API}?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"Error fetching TRM: {e}", file=sys.stderr)
        return []

    results = []
    for entry in data:
        results.append({
            "date": entry.get("vigenciadesde", "")[:10],
            "valor": float(entry.get("valor", 0)),
        })

    return sorted(results, key=lambda x: x["date"])


# ---------------------------------------------------------------------------
# Display formatters
# ---------------------------------------------------------------------------

def display_prices(data: dict, as_json: bool):
    if as_json:
        print(json.dumps(data, indent=2))
        return

    for ticker, records in data.items():
        if not records:
            continue
        print(f"\n{'='*65}")
        print(f"  {ticker} — Price History ({len(records)} records)")
        print(f"{'='*65}")

        # Show summary
        latest = records[-1]
        earliest = records[0]
        change = latest["close"] - earliest["close"]
        change_pct = (change / earliest["close"] * 100) if earliest["close"] else 0
        print(f"  Latest: ${latest['close']:,.2f} ({latest['date']})")
        print(f"  Period return: {change_pct:+.2f}%\n")

        # Show last 10 rows
        show = records[-10:]
        headers = ["Date", "Open", "High", "Low", "Close", "Volume"]
        rows = []
        for r in show:
            rows.append([
                r["date"],
                f"${r['open']:,.2f}",
                f"${r['high']:,.2f}",
                f"${r['low']:,.2f}",
                f"${r['close']:,.2f}",
                f"{r['volume']:,}",
            ])
        if len(records) > 10:
            print(f"  (showing last 10 of {len(records)} records)\n")
        _print_table(headers, rows, [12, 12, 12, 12, 12, 14])


def display_fundamentals(data: dict, as_json: bool):
    if as_json:
        print(json.dumps(data, indent=2))
        return

    for ticker, info in data.items():
        print(f"\n{'='*65}")
        print(f"  {ticker} — Fundamentals")
        print(f"{'='*65}")

        sections = [
            ("Valuation", [
                ("Market Cap", _fmt_number(info.get("market_cap"))),
                ("P/E (Trailing)", _fmt_number(info.get("pe_trailing"))),
                ("P/E (Forward)", _fmt_number(info.get("pe_forward"))),
                ("P/B Ratio", _fmt_number(info.get("pb_ratio"))),
                ("P/S Ratio", _fmt_number(info.get("ps_ratio"))),
                ("EV/EBITDA", _fmt_number(info.get("ev_ebitda"))),
            ]),
            ("Profitability", [
                ("ROE", f"{info['roe']*100:.1f}%" if info.get("roe") else "N/A"),
                ("ROA", f"{info['roa']*100:.1f}%" if info.get("roa") else "N/A"),
                ("Profit Margin", f"{info['profit_margin']*100:.1f}%" if info.get("profit_margin") else "N/A"),
                ("Operating Margin", f"{info['operating_margin']*100:.1f}%" if info.get("operating_margin") else "N/A"),
            ]),
            ("Financials", [
                ("Revenue", _fmt_number(info.get("revenue"))),
                ("Net Income", _fmt_number(info.get("net_income"))),
                ("Free Cash Flow", _fmt_number(info.get("free_cash_flow"))),
                ("Debt/Equity", _fmt_number(info.get("debt_to_equity"))),
                ("Current Ratio", _fmt_number(info.get("current_ratio"))),
            ]),
            ("Growth & Income", [
                ("Earnings Growth", f"{info['earnings_growth']*100:.1f}%" if info.get("earnings_growth") else "N/A"),
                ("Revenue Growth", f"{info['revenue_growth']*100:.1f}%" if info.get("revenue_growth") else "N/A"),
                ("Beta", _fmt_number(info.get("beta"))),
                ("Dividend Yield", f"{info['dividend_yield']*100:.2f}%" if info.get("dividend_yield") else "N/A"),
                ("Payout Ratio", f"{info['payout_ratio']*100:.1f}%" if info.get("payout_ratio") else "N/A"),
            ]),
        ]

        for section_name, items in sections:
            print(f"\n  {section_name}")
            print(f"  {'─'*40}")
            for label, value in items:
                print(f"    {label:<22s} {value}")


def display_profile(data: dict, as_json: bool):
    if as_json:
        print(json.dumps(data, indent=2))
        return

    for ticker, info in data.items():
        print(f"\n{'='*65}")
        print(f"  {ticker} — {info.get('name', 'N/A')}")
        print(f"{'='*65}")

        fields = [
            ("Sector", info.get("sector")),
            ("Industry", info.get("industry")),
            ("Country", info.get("country")),
            ("Employees", f"{info['employees']:,}" if info.get("employees") else None),
            ("Website", info.get("website")),
            ("Exchange", info.get("exchange")),
            ("Currency", info.get("currency")),
            ("Market Cap", _fmt_number(info.get("market_cap"))),
            ("52-Week High", f"${info['52w_high']:,.2f}" if info.get("52w_high") else None),
            ("52-Week Low", f"${info['52w_low']:,.2f}" if info.get("52w_low") else None),
            ("Avg Volume", f"{info['avg_volume']:,}" if info.get("avg_volume") else None),
        ]

        for label, value in fields:
            if value:
                print(f"  {label:<20s} {value}")

        summary = info.get("summary")
        if summary:
            print(f"\n  {summary}{'...' if len(summary) >= 300 else ''}")


def display_dividends(data: dict, as_json: bool):
    if as_json:
        print(json.dumps(data, indent=2))
        return

    for ticker, records in data.items():
        print(f"\n{'='*65}")
        print(f"  {ticker} — Dividend History ({len(records)} payments)")
        print(f"{'='*65}")

        if not records:
            print("  No dividend history found.")
            continue

        # Annual summary
        annual = {}
        for r in records:
            year = r["date"][:4]
            annual[year] = annual.get(year, 0) + r["dividend"]

        print("\n  Annual Dividends")
        print(f"  {'─'*30}")
        for year in sorted(annual.keys())[-10:]:
            print(f"    {year}    ${annual[year]:,.4f}")

        # Last 10 individual payments
        show = records[-10:]
        if len(records) > 10:
            print(f"\n  (showing last 10 of {len(records)} payments)")
        print()
        headers = ["Date", "Dividend"]
        rows = [[r["date"], f"${r['dividend']:,.4f}"] for r in show]
        _print_table(headers, rows, [14, 14])


def display_crypto(data: dict, as_json: bool):
    if as_json:
        print(json.dumps(data, indent=2))
        return

    for symbol, info in data.items():
        current = info.get("current", {})
        history = info.get("history", [])

        print(f"\n{'='*65}")
        print(f"  {symbol} — {current.get('name', 'N/A')}")
        print(f"{'='*65}")

        fields = [
            ("Price (USD)", f"${current['price_usd']:,.2f}" if current.get("price_usd") else "N/A"),
            ("Market Cap", _fmt_number(current.get("market_cap"))),
            ("24h Volume", _fmt_number(current.get("volume_24h"))),
            ("24h Change", f"{current['change_24h_pct']:+.2f}%" if current.get("change_24h_pct") is not None else "N/A"),
            ("7d Change", f"{current['change_7d_pct']:+.2f}%" if current.get("change_7d_pct") is not None else "N/A"),
            ("30d Change", f"{current['change_30d_pct']:+.2f}%" if current.get("change_30d_pct") is not None else "N/A"),
            ("ATH", f"${current['ath']:,.2f} ({current.get('ath_date', '')})" if current.get("ath") else "N/A"),
            ("Circulating Supply", f"{current['circulating_supply']:,.0f}" if current.get("circulating_supply") else "N/A"),
            ("Max Supply", f"{current['max_supply']:,.0f}" if current.get("max_supply") else "Unlimited"),
        ]

        for label, value in fields:
            print(f"  {label:<22s} {value}")

        if history:
            print(f"\n  Price History (last 10 of {len(history)} points)")
            print(f"  {'─'*30}")
            for pt in history[-10:]:
                print(f"    {pt['date']}  ${pt['price']:,.2f}")


def display_macro(data: dict, as_json: bool):
    if as_json:
        print(json.dumps(data, indent=2))
        return

    for sid, info in data.items():
        records = info.get("data", [])
        print(f"\n{'='*65}")
        print(f"  {sid} — {info.get('title', 'N/A')}")
        print(f"  Units: {info.get('units', '')}  |  Frequency: {info.get('frequency', '')}")
        print(f"{'='*65}")

        if not records:
            print("  No data.")
            continue

        latest = records[-1]
        print(f"  Latest: {latest['value']} ({latest['date']})\n")

        show = records[-20:]
        if len(records) > 20:
            print(f"  (showing last 20 of {len(records)} observations)\n")
        headers = ["Date", "Value"]
        rows = [[r["date"], f"{r['value']:,.4f}"] for r in show]
        _print_table(headers, rows, [14, 16])


def display_trm(rates: list, as_json: bool):
    if as_json:
        print(json.dumps(rates, indent=2))
        return

    print(f"\n{'='*65}")
    print(f"  TRM (USD/COP) — {len(rates)} rates")
    print(f"{'='*65}")

    if not rates:
        print("  No TRM data found.")
        return

    latest = rates[-1]
    print(f"  Latest: ${latest['valor']:,.2f} COP/USD ({latest['date']})\n")

    show = rates[-20:]
    if len(rates) > 20:
        print(f"  (showing last 20 of {len(rates)} rates)\n")
    headers = ["Date", "TRM (COP/USD)"]
    rows = [[r["date"], f"${r['valor']:,.2f}"] for r in show]
    _print_table(headers, rows, [14, 16])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Unified market data retrieval (investment-management mode 10)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Data sources (optional libraries):
  Stock prices, fundamentals, profile, dividends:  pip install yfinance
  Crypto prices and market data:                   pip install pycoingecko
  FRED macro series (GDP, CPI, etc.):              pip install fredapi
  TRM (USD/COP):                                   built-in (requests only)

Examples:
  %(prog)s --ticker AAPL --type price --period 1y
  %(prog)s --tickers AAPL,MSFT,GOOG --type price
  %(prog)s --ticker AAPL --type fundamentals
  %(prog)s --ticker AAPL --type profile
  %(prog)s --crypto BTC,ETH --type crypto --period 6m
  %(prog)s --macro GDP,CPI,UNRATE --type macro --period 5y
  %(prog)s --trm --period 30d
  %(prog)s --ticker AAPL --type price --json
""",
    )

    parser.add_argument("--ticker", help="Single ticker symbol (e.g., AAPL)")
    parser.add_argument("--tickers", help="Comma-separated tickers (e.g., AAPL,MSFT,GOOG)")
    parser.add_argument("--crypto", help="Crypto symbol(s) (e.g., BTC or BTC,ETH,SOL)")
    parser.add_argument("--macro", help="FRED series IDs (e.g., GDP,CPI,UNRATE)")
    parser.add_argument("--trm", action="store_true", help="Fetch Colombian TRM (USD/COP)")
    parser.add_argument(
        "--type",
        choices=["price", "fundamentals", "profile", "dividends", "macro", "crypto"],
        default="price",
        help="Data type to fetch (default: price)",
    )
    parser.add_argument(
        "--period",
        default="1y",
        help="Historical period: 1d, 5d, 1m, 3m, 6m, 1y, 2y, 5y, 10y, max, or Nd (default: 1y)",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    ensure_dirs()

    # Resolve ticker list
    tickers = []
    if args.ticker:
        tickers = [args.ticker.upper()]
    elif args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]

    # Dispatch based on flags and type
    if args.trm:
        rates = fetch_trm(args.period)
        display_trm(rates, args.json)
        return

    if args.macro:
        series_ids = [s.strip().upper() for s in args.macro.split(",") if s.strip()]
        data = fetch_macro(series_ids, args.period)
        display_macro(data, args.json)
        return

    if args.crypto:
        symbols = [s.strip().upper() for s in args.crypto.split(",") if s.strip()]
        data = fetch_crypto(symbols, args.period)
        display_crypto(data, args.json)
        return

    # Stock/ETF data types
    if not tickers:
        parser.error("Provide --ticker or --tickers for stock data, or use --crypto, --macro, --trm")

    if args.type == "price":
        data = fetch_stock_prices(tickers, args.period)
        display_prices(data, args.json)
    elif args.type == "fundamentals":
        data = fetch_fundamentals(tickers)
        display_fundamentals(data, args.json)
    elif args.type == "profile":
        data = fetch_profile(tickers)
        display_profile(data, args.json)
    elif args.type == "dividends":
        data = fetch_dividends(tickers)
        display_dividends(data, args.json)
    elif args.type == "crypto":
        # Allow --ticker BTC --type crypto as well
        data = fetch_crypto(tickers, args.period)
        display_crypto(data, args.json)
    elif args.type == "macro":
        # Allow --ticker GDP --type macro as well
        data = fetch_macro(tickers, args.period)
        display_macro(data, args.json)
    else:
        parser.error(f"Unknown type: {args.type}")


if __name__ == "__main__":
    main()
