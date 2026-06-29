#!/usr/bin/env python3
"""
OpenBB-backed data adapter for investment-management (mode 10 / market_data).

Drop-in backend for `market_data.py`: every public `fetch_*` function returns the
EXACT same dict/list shapes as the yfinance/coingecko/fred implementations, so the
`display_*` formatters and CLI keep working unchanged. The win is consolidation —
one `obb.*` namespace (17 providers) replaces three hand-wired clients — plus
capabilities the legacy module never had (options chains, analyst estimates) and a
direct Kronos OHLCV feeder for the trading-decision-plane.

All endpoints below run FREE on the yfinance provider (no API keys). FRED macro
needs a free FRED key (same as the legacy backend); ETF holdings need an fmp/intrinio
free-tier key.

Verified empirically against openbb 4.7.2 — see research/entities/tool/openbb.md (BRO-1410).

Usage:
    python3 openbb_adapter.py --self-test           # live smoke (P11), per-field coverage
    python3 openbb_adapter.py --kronos AAPL --period 1y

License note: OpenBB ODP is AGPLv3. Fine as a local/internal tool. If ever embedded
in a distributed hosted product, keep it process-isolated behind the MCP boundary
(openbb-mcp-server) and review the license posture before shipping.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta

PERIOD_DAYS = {
    "1d": 1, "5d": 5, "1m": 30, "3m": 90, "6m": 180,
    "1y": 365, "2y": 730, "5y": 1825, "10y": 3650, "max": 10000,
}

_OBB = None


def _obb():
    """Lazy singleton — importing obb triggers a one-time asset build, so defer it."""
    global _OBB
    if _OBB is None:
        try:
            from openbb import obb
        except ImportError as e:  # pragma: no cover - environment guard
            print(
                "Error: openbb is required for the OpenBB backend.\n"
                "  Install: pip install openbb openbb-mcp-server",
                file=sys.stderr,
            )
            raise SystemExit(1) from e
        _OBB = obb
    return _OBB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _period_to_days(period: str) -> int:
    if period.endswith("d") and period[:-1].isdigit():
        return int(period[:-1])
    return PERIOD_DAYS.get(period, 365)


def _start_date(period: str) -> str:
    return (datetime.now() - timedelta(days=_period_to_days(period))).strftime("%Y-%m-%d")


def _to_df(obbject):
    """OBBject -> DataFrame (handles the .to_df alias)."""
    if hasattr(obbject, "to_dataframe"):
        return obbject.to_dataframe()
    return obbject.to_df()


def _pick(d: dict, *keys):
    """First non-null value among candidate keys (OpenBB field names drift by provider)."""
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


def _date_str(idx) -> str:
    try:
        return idx.strftime("%Y-%m-%d")
    except AttributeError:
        return str(idx)[:10]


def _isnan(v) -> bool:
    """True for None or float NaN (NaN != NaN), without importing pandas."""
    return v is None or (isinstance(v, float) and v != v)


def _pct_to_frac(v):
    """OpenBB's yfinance metrics report dividend_yield in PERCENT (0.35 = 0.35%), but
    display_fundamentals multiplies by 100 expecting a fraction. Normalize to a fraction."""
    return v / 100 if v is not None else None


def _ohlcv_records(df) -> list[dict]:
    """Normalize a price/OHLCV DataFrame to the legacy record list.

    Drops data-gap bars where any OHLC value is NaN/None — matches legacy yfinance
    `.history()` (which drops them) and prevents `$nan` rendering through display_prices.
    """
    records = []
    has_date_col = "date" in df.columns
    for idx, row in df.iterrows():
        o, hi, lo, c = row.get("open"), row.get("high"), row.get("low"), row.get("close")
        if any(_isnan(v) for v in (o, hi, lo, c)):
            continue
        date = _date_str(row["date"]) if has_date_col else _date_str(idx)
        vol = row.get("volume")
        records.append({
            "date": date,
            "open": round(float(o), 2),
            "high": round(float(hi), 2),
            "low": round(float(lo), 2),
            "close": round(float(c), 2),
            "volume": int(vol) if not _isnan(vol) else 0,
        })
    return records


# ---------------------------------------------------------------------------
# Public API — identical contracts to market_data.py
# ---------------------------------------------------------------------------

def fetch_stock_prices(tickers: list[str], period: str) -> dict:
    """{ticker: [{date, open, high, low, close, volume}, ...]} — via obb.equity.price.historical."""
    obb = _obb()
    start = _start_date(period)
    results = {}
    for ticker in tickers:
        try:
            df = _to_df(obb.equity.price.historical(ticker, start_date=start, provider="yfinance"))
            if df is None or df.empty:
                print(f"  Warning: no price data for {ticker}", file=sys.stderr)
                continue
            results[ticker] = _ohlcv_records(df)
        except Exception as e:  # noqa: BLE001
            print(f"  Error fetching {ticker}: {e}", file=sys.stderr)
    return results


def fetch_fundamentals(tickers: list[str]) -> dict:
    """Legacy fundamentals dict — via obb.equity.fundamental.metrics (+ quote for beta/52w)."""
    obb = _obb()
    results = {}
    for ticker in tickers:
        try:
            m = _to_df(obb.equity.fundamental.metrics(ticker, provider="yfinance"))
            row = m.iloc[0].to_dict() if not m.empty else {}
            # best-effort enrichment from quote (beta, dividend yield sometimes live here)
            q = {}
            try:
                qdf = _to_df(obb.equity.price.quote(ticker, provider="yfinance"))
                q = qdf.iloc[0].to_dict() if not qdf.empty else {}
            except Exception:  # noqa: BLE001
                pass
            # revenue / net_income / fcf live on the statements, not the metrics model;
            # one income-statement call closes the value-screening parity gap.
            inc = {}
            try:
                idf = _to_df(obb.equity.fundamental.income(ticker, limit=1, provider="yfinance"))
                inc = idf.iloc[-1].to_dict() if not idf.empty else {}
            except Exception:  # noqa: BLE001
                pass
            revenue = _pick(row, "revenue", "total_revenue") or _pick(inc, "total_revenue", "operating_revenue", "revenue")
            net_income = _pick(row, "net_income", "net_income_common") or _pick(inc, "net_income", "consolidated_net_income")
            mcap = _pick(row, "market_cap", "marketcap")
            ps_ratio = _pick(row, "price_to_sales", "ps_ratio")
            if ps_ratio is None and mcap and revenue:
                try:
                    ps_ratio = round(float(mcap) / float(revenue), 4)
                except (ValueError, ZeroDivisionError):
                    ps_ratio = None
            results[ticker] = {
                "market_cap": _pick(row, "market_cap", "marketcap"),
                "pe_trailing": _pick(row, "pe_ratio", "pe", "trailing_pe"),
                "pe_forward": _pick(row, "forward_pe", "forward_pe_ratio"),
                "pb_ratio": _pick(row, "price_to_book", "pb_ratio"),
                "ps_ratio": ps_ratio,
                "ev_ebitda": _pick(row, "enterprise_to_ebitda", "ev_to_ebitda"),
                "roe": _pick(row, "return_on_equity", "roe"),
                "roa": _pick(row, "return_on_assets", "roa"),
                "profit_margin": _pick(row, "profit_margin", "net_profit_margin", "profit_margins"),
                "operating_margin": _pick(row, "operating_margin", "operating_profit_margin"),
                "revenue": revenue,
                "net_income": net_income,
                "free_cash_flow": _pick(row, "free_cash_flow", "fcf") or _pick(inc, "free_cash_flow"),
                "debt_to_equity": _pick(row, "debt_to_equity"),
                "current_ratio": _pick(row, "current_ratio"),
                "beta": _pick(row, "beta", *([] if not q else ["beta"])) or _pick(q, "beta"),
                "dividend_yield": _pct_to_frac(_pick(row, "dividend_yield") or _pick(q, "dividend_yield")),
                "payout_ratio": _pick(row, "payout_ratio"),
                "earnings_growth": _pick(row, "earnings_growth", "eps_growth"),
                "revenue_growth": _pick(row, "revenue_growth", "growth_revenue"),
            }
        except Exception as e:  # noqa: BLE001
            print(f"  Error fetching fundamentals for {ticker}: {e}", file=sys.stderr)
    return results


def fetch_profile(tickers: list[str]) -> dict:
    """Legacy profile dict — via obb.equity.profile (+ quote for 52w/avg_volume)."""
    obb = _obb()
    results = {}
    for ticker in tickers:
        try:
            p = _to_df(obb.equity.profile(ticker, provider="yfinance"))
            row = p.iloc[0].to_dict() if not p.empty else {}
            q = {}
            try:
                qdf = _to_df(obb.equity.price.quote(ticker, provider="yfinance"))
                q = qdf.iloc[0].to_dict() if not qdf.empty else {}
            except Exception:  # noqa: BLE001
                pass
            summary = _pick(row, "long_description", "business_summary") or ""
            results[ticker] = {
                "name": _pick(row, "name", "long_name", "short_name"),
                "sector": _pick(row, "sector"),
                "industry": _pick(row, "industry_category", "industry_group", "industry"),
                "country": _pick(row, "hq_country", "country"),
                "employees": _pick(row, "employees", "full_time_employees"),
                "website": _pick(row, "company_url", "website"),
                "exchange": _pick(row, "stock_exchange", "exchange"),
                "currency": _pick(row, "currency") or _pick(q, "currency"),
                "market_cap": _pick(row, "market_cap") or _pick(q, "market_cap"),
                "52w_high": _pick(q, "year_high", "fifty_two_week_high", "high_52w"),
                "52w_low": _pick(q, "year_low", "fifty_two_week_low", "low_52w"),
                "avg_volume": _pick(q, "avg_volume", "average_volume", "volume_avg"),
                "summary": str(summary)[:300],
            }
        except Exception as e:  # noqa: BLE001
            print(f"  Error fetching profile for {ticker}: {e}", file=sys.stderr)
    return results


def fetch_dividends(tickers: list[str]) -> dict:
    """{ticker: [{date, dividend}, ...]} — via obb.equity.fundamental.dividends."""
    obb = _obb()
    results = {}
    for ticker in tickers:
        try:
            df = _to_df(obb.equity.fundamental.dividends(ticker, provider="yfinance"))
            if df is None or df.empty:
                results[ticker] = []
                continue
            records = []
            has_date_col = "date" in df.columns
            for idx, row in df.iterrows():
                date = _date_str(row["date"]) if has_date_col else _date_str(idx)
                amount = _pick(row.to_dict(), "dividend", "amount", "value")
                if amount is None:
                    continue
                records.append({"date": date, "dividend": round(float(amount), 4)})
            results[ticker] = records
        except Exception as e:  # noqa: BLE001
            print(f"  Error fetching dividends for {ticker}: {e}", file=sys.stderr)
    return results


def fetch_crypto(symbols: list[str], period: str) -> dict:
    """{SYM: {current: {...}, history: [{date, price}]}} — via obb.crypto.price.historical.

    Note: OpenBB's default providers don't include CoinGecko, so market_cap / ath /
    circulating_supply are unavailable on the free path; price + change %s are derived
    from the OHLCV history. The legacy CoinGecko backend remains the source for those
    fields if richer 'current' market data is needed.
    """
    obb = _obb()
    start = _start_date(period)
    results = {}
    for symbol in symbols:
        sym = symbol.upper()
        pair = sym if "-" in sym else f"{sym}-USD"
        try:
            df = _to_df(obb.crypto.price.historical(pair, start_date=start, provider="yfinance"))
            history = []
            closes = []
            has_date_col = "date" in df.columns
            for idx, row in df.iterrows():
                c = row.get("close")
                if _isnan(c):
                    continue
                date = _date_str(row["date"]) if has_date_col else _date_str(idx)
                close = round(float(c), 2)
                history.append({"date": date, "price": close})
                closes.append(close)

            def _chg(n):
                if len(closes) > n and closes[-1 - n]:
                    return round((closes[-1] / closes[-1 - n] - 1) * 100, 2)
                return None

            current = {
                "name": sym,
                "symbol": sym,
                "price_usd": closes[-1] if closes else None,
                "market_cap": None,         # needs CoinGecko provider
                "volume_24h": int(df.iloc[-1]["volume"]) if not df.empty else None,
                "change_24h_pct": _chg(1),
                "change_7d_pct": _chg(7),
                "change_30d_pct": _chg(30),
                "ath": max(closes) if closes else None,  # ATH within window only
                "ath_date": "",
                "circulating_supply": None,  # needs CoinGecko provider
                "max_supply": None,
            }
            results[sym] = {"current": current, "history": history}
        except Exception as e:  # noqa: BLE001
            print(f"  Error fetching crypto {sym}: {e}", file=sys.stderr)
    return results


def fetch_macro(series_ids: list[str], period: str) -> dict:
    """{sid: {title, units, frequency, data: [{date, value}]}} — via obb.economy.fred_series.

    Requires a free FRED API key (set FRED_API_KEY or run `obb.user.credentials.fred_api_key`).
    Degrades gracefully to an empty series with a stderr note when the key is missing.
    """
    obb = _obb()
    start = _start_date(period)
    results = {}
    for sid in series_ids:
        try:
            res = obb.economy.fred_series(sid, start_date=start)
            df = _to_df(res)
            records = []
            has_date_col = "date" in df.columns
            for idx, row in df.iterrows():
                date = _date_str(row["date"]) if has_date_col else _date_str(idx)
                val = _pick(row.to_dict(), sid, "value", sid.lower())
                if val is None:
                    # single-value-column frame: take the first numeric cell
                    nums = [v for v in row.to_dict().values() if isinstance(v, (int, float))]
                    val = nums[0] if nums else None
                if val is None:
                    continue
                records.append({"date": date, "value": round(float(val), 4)})
            meta = {}
            try:
                meta = (res.extra or {}).get("metadata", {}).get(sid, {}) if hasattr(res, "extra") else {}
            except Exception:  # noqa: BLE001
                pass
            results[sid] = {
                "title": str(meta.get("title", sid)),
                "units": str(meta.get("units", "")),
                "frequency": str(meta.get("frequency", "")),
                "data": records,
            }
        except Exception as e:  # noqa: BLE001
            print(f"  Error fetching FRED series {sid}: {e} (needs free FRED key)", file=sys.stderr)
            results[sid] = {"title": sid, "units": "", "frequency": "", "data": []}
    return results


def fetch_trm(period: str) -> list:
    """[{date, valor}, ...] USD/COP — via obb.currency.price.historical (USDCOP=X).

    CAVEAT: this is the yfinance market spot rate, NOT Colombia's official TRM.
    For finance-substrate tax math (Form 210, patrimonio), the legally correct rate
    is the official TRM from datos.gov.co — use the default (yfinance) backend's
    fetch_trm for that. This OpenBB path is a market-rate approximation only.
    """
    obb = _obb()
    start = _start_date(period)
    try:
        df = _to_df(obb.currency.price.historical("USDCOP=X", start_date=start, provider="yfinance"))
    except Exception as e:  # noqa: BLE001
        print(f"Error fetching TRM: {e}", file=sys.stderr)
        return []
    results = []
    has_date_col = "date" in df.columns
    for idx, row in df.iterrows():
        c = row.get("close")
        if _isnan(c):
            continue
        date = _date_str(row["date"]) if has_date_col else _date_str(idx)
        results.append({"date": date, "valor": round(float(c), 2)})
    return sorted(results, key=lambda x: x["date"])


# ---------------------------------------------------------------------------
# New capabilities (no legacy equivalent)
# ---------------------------------------------------------------------------

def ohlcv_for_kronos(ticker: str, period: str = "1y"):
    """Return a Kronos-ready OHLCV DataFrame: columns [timestamps, open, high, low,
    close, volume, amount] where amount = close * volume (turnover proxy).

    Feeds the trading-decision-plane:
        df = ohlcv_for_kronos("AAPL", "2y")
        KronosPredictor.predict(df[["open","high","low","close","volume","amount"]],
                                x_timestamp=df["timestamps"], ...)
    """
    obb = _obb()
    start = _start_date(period)
    df = _to_df(obb.equity.price.historical(ticker, start_date=start, provider="yfinance"))
    df = df.reset_index()
    # locate the date column (reset_index names it 'date' or 'index')
    date_col = "date" if "date" in df.columns else df.columns[0]
    out = df[[date_col, "open", "high", "low", "close", "volume"]].copy()
    out = out.rename(columns={date_col: "timestamps"})
    out["amount"] = out["close"] * out["volume"]
    return out


def options_chain(ticker: str):
    """Full options chain DataFrame (strike, expiration, option_type, oi, iv, greeks).
    Free via yfinance — the legacy module had no options support (Taleb barbell input)."""
    obb = _obb()
    return _to_df(obb.derivatives.options.chains(ticker, provider="yfinance"))


def estimates(ticker: str) -> dict:
    """Analyst consensus (target price, recommendation, #analysts) — score.py momentum input."""
    obb = _obb()
    df = _to_df(obb.equity.estimates.consensus(ticker, provider="yfinance"))
    return df.iloc[0].to_dict() if not df.empty else {}


# ---------------------------------------------------------------------------
# Self-test (P11 live smoke)
# ---------------------------------------------------------------------------

def _self_test() -> int:
    print("OpenBB adapter self-test (live, no API keys)\n" + "=" * 60)
    ok = 0
    total = 0

    def check(label, fn):
        nonlocal ok, total
        total += 1
        try:
            out = fn()
            print(f"  [OK ] {label}: {out}")
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"  [ERR] {label}: {str(e)[:120]}")

    px = fetch_stock_prices(["AAPL"], "1m")
    check("prices(AAPL,1m)", lambda: f"{len(px.get('AAPL', []))} bars, last={px['AAPL'][-1]}")

    fu = fetch_fundamentals(["AAPL"])
    f = fu.get("AAPL", {})
    populated = {k: v for k, v in f.items() if v is not None}
    check("fundamentals(AAPL)", lambda: f"{len(populated)}/{len(f)} fields populated: {sorted(populated)}")

    pr = fetch_profile(["AAPL"])
    p = pr.get("AAPL", {})
    pop_p = {k: v for k, v in p.items() if v not in (None, "")}
    check("profile(AAPL)", lambda: f"{len(pop_p)}/{len(p)} fields: name={p.get('name')}, sector={p.get('sector')}")

    dv = fetch_dividends(["AAPL"])
    check("dividends(AAPL)", lambda: f"{len(dv.get('AAPL', []))} payments")

    cr = fetch_crypto(["BTC"], "1m")
    c = cr.get("BTC", {})
    check("crypto(BTC,1m)", lambda: f"{len(c.get('history', []))} bars, price=${c.get('current', {}).get('price_usd')}, 7d={c.get('current', {}).get('change_7d_pct')}%")

    trm = fetch_trm("1m")
    check("trm(USDCOP,1m)", lambda: f"{len(trm)} days, latest={trm[-1] if trm else None}")

    kr = ohlcv_for_kronos("AAPL", "3m")
    check("ohlcv_for_kronos(AAPL,3m)", lambda: f"{kr.shape} cols={list(kr.columns)}, amount[-1]={kr['amount'].iloc[-1]:.0f}")

    est = estimates("AAPL")
    check("estimates(AAPL)", lambda: f"target_consensus={est.get('target_consensus')}, rec={est.get('recommendation')}")

    oc = options_chain("AAPL")
    check("options_chain(AAPL)", lambda: f"{oc.shape} contracts")

    # FRED needs a key — report but don't fail the suite
    mc = fetch_macro(["DGS10"], "1m")
    n = len(mc.get("DGS10", {}).get("data", []))
    print(f"  [{'OK ' if n else 'KEY'}] macro(DGS10): {n} obs" + ("" if n else " (needs free FRED key)"))

    print("=" * 60)
    print(f"SELF-TEST: {ok}/{total} core endpoints OK (FRED macro excluded — needs free key)")
    return 0 if ok == total else 1


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="OpenBB-backed data adapter for investment-management")
    ap.add_argument("--self-test", action="store_true", help="Run live smoke test (P11)")
    ap.add_argument("--kronos", metavar="TICKER", help="Print Kronos-ready OHLCV df for TICKER")
    ap.add_argument("--period", default="1y")
    args = ap.parse_args()

    if args.kronos:
        df = ohlcv_for_kronos(args.kronos.upper(), args.period)
        print(df.tail(10).to_string())
        print(f"\nshape={df.shape} columns={list(df.columns)}")
        return 0
    # default action is the self-test
    return _self_test()


if __name__ == "__main__":
    raise SystemExit(main())
