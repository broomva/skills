#!/usr/bin/env python3
"""Render a self-contained, privacy-safe harness usage HTML report."""

from __future__ import annotations

import html
from typing import Any


TOKEN_FIELDS = (
    ("input_uncached", "Uncached input", "input"),
    ("cache_read", "Cache read", "cache"),
    ("cache_write_5m", "Cache write 5m", "write"),
    ("cache_write_1h", "Cache write 1h", "write-long"),
    ("output", "Output", "output"),
    ("reasoning", "Reasoning", "reasoning"),
    ("tool", "Tool", "tool"),
)


def escaped(value: Any) -> str:
    return html.escape(str(value), quote=True)


def comment_value(value: Any) -> str:
    return escaped(str(value).replace("--", "- -").replace("\r", " ").replace("\n", " "))


def format_tokens(value: int | float | None) -> str:
    numeric = max(0, int(value or 0))
    for suffix, divisor in (("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)):
        if numeric >= divisor:
            return f"{numeric / divisor:.2f}{suffix}"
    return f"{numeric:,}"


def format_money(value: float | None) -> str:
    if value is None:
        return "Unknown"
    if 0 < value < 0.01:
        return f"${value:.4f}"
    return f"${value:,.2f}"


def format_percent(value: float | None) -> str:
    return "Unknown" if value is None else f"{max(0.0, min(1.0, value)):.1%}"


def cost_summary(report: dict[str, Any]) -> tuple[str, str]:
    overall = report["overall"]
    if not overall.get("total_tokens") and not report.get("quota_windows"):
        return "No trace usage", "No token events found"
    if overall.get("estimated_cost_usd") is not None:
        return format_money(overall["estimated_cost_usd"]), "Complete public API list-price estimate"
    partial = overall.get("estimated_cost_usd_priced_portion") or 0
    if partial:
        coverage = format_percent(overall.get("pricing_coverage"))
        return format_money(partial), f"Priced portion only · {coverage} coverage"
    if report.get("quota_windows") and not overall.get("events"):
        return "Not exposed", "Quota status does not include tokens or cost"
    return "Unpriced", "No complete model-price match"


def improvement_opportunities(report: dict[str, Any]) -> list[dict[str, str]]:
    """Return bounded review signals whose evidence is present in the report."""
    overall = report["overall"]
    total = int(overall.get("total_tokens") or 0)
    opportunities: list[dict[str, str]] = []

    if total:
        coverage = overall.get("pricing_coverage")
        if coverage is None:
            opportunities.append({
                "kind": "pricing",
                "title": "Establish pricing coverage",
                "evidence": "Pricing coverage is unknown.",
                "action": "Resolve model attribution before treating the estimated cost as complete.",
            })
        elif float(coverage) < 1:
            opportunities.append({
                "kind": "pricing",
                "title": "Close the pricing coverage gap",
                "evidence": f"{float(coverage):.1%} of tokens have a resolved rate.",
                "action": "Map unknown model identifiers or refresh the reviewed rate snapshot before treating cost as complete.",
            })

        input_basis = sum(int(overall.get(field) or 0) for field in (
            "input_uncached", "cache_read", "cache_write_5m", "cache_write_1h",
        ))
        if input_basis:
            cache_share = int(overall.get("cache_read") or 0) / input_basis
            if cache_share < 0.2:
                opportunities.append({
                    "kind": "cache",
                    "title": "Review cache reuse",
                    "evidence": f"Cache reads are {cache_share:.1%} of normalized input.",
                    "action": "If workloads repeat stable context, inspect prompt stability and reusable context boundaries.",
                })

        rows = report.get("by_model", [])
        if rows:
            top = rows[0]
            share = int(top.get("total_tokens") or 0) / total
            if share >= 0.5:
                opportunities.append({
                    "kind": "routing",
                    "title": "Review model concentration",
                    "evidence": f"{top.get('provider', 'unknown')}/{top.get('model', 'unknown')} carries {share:.1%} of tokens.",
                    "action": "Check whether routine work can use a lower-cost model without compromising required quality.",
                })

        output_tokens = sum(int(overall.get(field) or 0) for field in ("output", "reasoning", "tool"))
        output_share = output_tokens / total
        if output_share >= 0.4:
            opportunities.append({
                "kind": "output",
                "title": "Inspect output-heavy work",
                "evidence": f"Output, reasoning, and tool tokens are {output_share:.1%} of total volume.",
                "action": "Review response-length and tool-loop requirements where shorter completion criteria are acceptable.",
            })

    diagnostics = report.get("diagnostics", {})
    accounting_gaps = (
        int(diagnostics.get("codex_unresolved_forks") or 0)
        + int(diagnostics.get("codex_unresolved_total_only_rows") or 0)
        + int(diagnostics.get("codex_ambiguous_copied_prefixes") or 0)
    )
    if accounting_gaps:
        opportunities.append({
            "kind": "quality",
            "title": "Resolve accounting gaps first",
            "evidence": f"{accounting_gaps:,} unresolved Codex lineage gap(s) can affect normalized totals.",
            "action": "Reconcile these diagnostics before using the headline for a budget or routing decision.",
        })

    pressured = [
        window for window in report.get("quota_windows", [])
        if window.get("usage_known") and window.get("remaining_fraction") is not None
        and float(window["remaining_fraction"]) <= 0.2
    ]
    if pressured:
        lowest = min(pressured, key=lambda item: float(item["remaining_fraction"]))
        opportunities.append({
            "kind": "quota",
            "title": "Plan around quota pressure",
            "evidence": f"{lowest.get('title', 'A quota window')} has {format_percent(lowest.get('remaining_fraction'))} remaining.",
            "action": "Consider deferring non-urgent work or routing eligible tasks until quota resets.",
        })

    if not opportunities:
        if not total and not report.get("quota_windows"):
            opportunities.append({
                "kind": "monitor",
                "title": "No trace usage found",
                "evidence": "No normalized token events or quota windows were discovered.",
                "action": "Check provider paths and the selected time window before optimizing.",
            })
        else:
            opportunities.append({
                "kind": "monitor",
                "title": "Preserve the current measurement baseline",
                "evidence": "No configured mechanical risk threshold fired in this report.",
                "action": "Compare the next equivalent window before changing model routing or context strategy.",
            })
    return opportunities[:6]


def _metric(label: str, value: str, note: str) -> str:
    return (
        '<article class="metric">'
        f'<p class="eyebrow">{escaped(label)}</p>'
        f'<p class="metric-value">{escaped(value)}</p>'
        f'<p class="metric-note">{escaped(note)}</p>'
        "</article>"
    )


def _token_composition(overall: dict[str, Any]) -> str:
    total = max(0, int(overall.get("total_tokens") or 0))
    segments: list[str] = []
    legend: list[str] = []
    for field, label, css_class in TOKEN_FIELDS:
        value = max(0, int(overall.get(field) or 0))
        share = value / total if total else 0
        if value:
            segments.append(
                f'<span class="segment {css_class}" style="width:{share:.6%}" '
                f'title="{escaped(label)}: {format_tokens(value)} ({share:.1%})"></span>'
            )
        legend.append(
            '<li>'
            f'<span class="swatch {css_class}"></span><span>{escaped(label)}</span>'
            f'<strong>{format_tokens(value)}</strong>'
            "</li>"
        )
    bar = "".join(segments) or '<span class="segment empty" style="width:100%"></span>'
    return (
        '<div class="composition">'
        f'<div class="composition-bar" aria-hidden="true">{bar}</div>'
        f'<ul class="legend" aria-label="Token composition details">{"".join(legend)}</ul>'
        "</div>"
    )


def _model_rows(report: dict[str, Any]) -> str:
    total = max(0, int(report["overall"].get("total_tokens") or 0))
    rows: list[str] = []
    for row in report.get("by_model", []):
        tokens = max(0, int(row.get("total_tokens") or 0))
        share = tokens / total if total else 0
        cost = row.get("estimated_cost_usd")
        if cost is None and row.get("estimated_cost_usd_priced_portion"):
            cost_text = f"{format_money(row['estimated_cost_usd_priced_portion'])} partial"
        else:
            cost_text = format_money(cost)
        rows.append(
            "<tr>"
            f'<td><span class="provider">{escaped(row.get("provider", "unknown"))}</span></td>'
            f'<td><strong>{escaped(row.get("model", "unknown"))}</strong></td>'
            f'<td class="number">{format_tokens(tokens)}</td>'
            f'<td><div class="share-track"><span style="width:{share:.6%}"></span></div><small>{share:.1%}</small></td>'
            f'<td class="number">{escaped(cost_text)}</td>'
            f'<td class="number">{int(row.get("events") or 0):,}</td>'
            "</tr>"
        )
    if not rows:
        return '<p class="empty-state">No trace-level model usage is available for this selection.</p>'
    return (
        '<div class="table-wrap"><table>'
        '<caption class="sr-only">Usage aggregated by provider and model</caption>'
        "<thead><tr><th>Provider</th><th>Model</th><th>Tokens</th><th>Share</th><th>Estimated cost</th><th>Events</th></tr></thead>"
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )


def _quota_cards(report: dict[str, Any]) -> str:
    cards: list[str] = []
    for window in report.get("quota_windows", []):
        remaining = window.get("remaining_fraction")
        remaining_text = format_percent(remaining)
        reset = window.get("resets_at") or "Reset time unavailable"
        title = window.get("title", "Quota")
        if remaining is None:
            track = (
                '<div class="quota-track unavailable" '
                f'aria-label="{escaped(title)} usage unavailable"></div>'
            )
        else:
            remaining_value = max(0.0, min(1.0, float(remaining)))
            track = (
                '<div class="quota-track" role="progressbar" '
                f'aria-label="{escaped(title)} remaining" aria-valuemin="0" aria-valuemax="100" '
                f'aria-valuenow="{remaining_value * 100:.1f}"><span style="width:{remaining_value:.6%}"></span></div>'
            )
        cards.append(
            '<article class="quota-card">'
            f'<div><p class="eyebrow">{escaped(window.get("family", "quota"))}</p>'
            f'<h3>{escaped(title)}</h3></div>'
            f'<p class="quota-value">{escaped(remaining_text)} <span>remaining</span></p>'
            f'{track}'
            f'<p class="muted">Resets: {escaped(reset)}</p>'
            "</article>"
        )
    return "".join(cards)


def _provider_cost_section(report: dict[str, Any]) -> str:
    overall = report["overall"]
    cards = []
    if overall.get("reported_list_cost_usd") is not None:
        cards.append(_metric(
            "Vendor-reported list cost",
            format_money(overall["reported_list_cost_usd"]),
            "Provider-supplied value; do not add to the API estimate",
        ))
    if overall.get("charged_cost_usd") is not None:
        cards.append(_metric(
            "Plan-deducted cost",
            format_money(overall["charged_cost_usd"]),
            "Provider-supplied metered deduction",
        ))
    if not cards:
        return ""
    return (
        '<section><div class="section-heading"><div><p class="eyebrow">Provider measurement</p>'
        '<h2>Reported cost</h2></div><p>Kept separate from the API-equivalent estimate.</p></div>'
        f'<div class="metrics provider-costs">{"".join(cards)}</div></section>'
    )


def _insight_items(report: dict[str, Any]) -> str:
    items = [f'<li>{escaped(item.get("message", ""))}</li>' for item in report.get("insights", [])]
    return "".join(items) or "<li>No deterministic insight signal was emitted.</li>"


def _opportunity_cards(report: dict[str, Any]) -> str:
    cards: list[str] = []
    for opportunity in improvement_opportunities(report):
        cards.append(
            f'<article class="opportunity {escaped(opportunity["kind"])}">'
            f'<p class="eyebrow">{escaped(opportunity["kind"])}</p>'
            f'<h3>{escaped(opportunity["title"])}</h3>'
            f'<p class="evidence">{escaped(opportunity["evidence"])}</p>'
            f'<p>{escaped(opportunity["action"])}</p>'
            "</article>"
        )
    return "".join(cards)


def _diagnostics(report: dict[str, Any]) -> str:
    diagnostics = report.get("diagnostics", {})
    provider_rows = []
    for provider, backend in sorted(diagnostics.get("backends", {}).items()):
        quota_backend = diagnostics.get("quota_backends", {}).get(provider)
        detail = f" · {quota_backend}" if quota_backend else ""
        files = int(diagnostics.get("files_scanned", {}).get(provider, 0))
        provider_rows.append(
            "<tr>"
            f"<td>{escaped(provider)}</td><td>{escaped(str(backend) + detail)}</td><td class=\"number\">{files:,}</td>"
            "</tr>"
        )
    warnings = diagnostics.get("warnings", [])
    warning_items = "".join(f"<li>{escaped(warning)}</li>" for warning in warnings)
    if not warning_items:
        warning_items = "<li>No scanner warnings.</li>"
    files = sum(int(value or 0) for value in diagnostics.get("files_scanned", {}).values())
    malformed = sum(int(value or 0) for value in diagnostics.get("malformed_rows", {}).values())
    unresolved = (
        int(diagnostics.get("codex_unresolved_forks") or 0)
        + int(diagnostics.get("codex_unresolved_total_only_rows") or 0)
        + int(diagnostics.get("codex_ambiguous_copied_prefixes") or 0)
    )
    facts = (
        '<div class="facts">'
        f'<span><strong>{files:,}</strong> files scanned</span>'
        f'<span><strong>{malformed:,}</strong> malformed rows</span>'
        f'<span><strong>{unresolved:,}</strong> unresolved Codex gaps</span>'
        "</div>"
    )
    return (
        facts
        + '<div class="diagnostic-grid">'
        '<div class="table-wrap"><table><caption class="sr-only">Scanner backend by provider</caption><thead><tr><th>Provider</th><th>Backend</th><th>Files scanned</th></tr></thead>'
        f'<tbody>{"".join(provider_rows)}</tbody></table></div>'
        f'<div class="warnings"><h3>Warnings</h3><ul>{warning_items}</ul></div>'
        "</div>"
    )


def render_html(report: dict[str, Any]) -> str:
    overall = report["overall"]
    cost, cost_note = cost_summary(report)
    providers = sorted(report.get("diagnostics", {}).get("backends", {}))
    provider_chips = "".join(f'<span class="chip">{escaped(provider)}</span>' for provider in providers)
    pricing = report.get("pricing", {})
    coverage = (
        "Not applicable"
        if not overall.get("total_tokens")
        else format_percent(overall.get("pricing_coverage"))
    )
    provider_cost_section = _provider_cost_section(report)
    window_days = report.get("window_days")
    window_value = (
        f"{int(window_days):,} day" + ("s" if int(window_days) != 1 else "")
        if window_days is not None
        else "Custom"
    )
    quota_section = ""
    if report.get("quota_windows"):
        quota_section = (
            '<section><div class="section-heading"><div><p class="eyebrow">Live status</p>'
            '<h2>Quota windows</h2></div><p>Current allowances, excluded from token and cost totals.</p></div>'
            f'<div class="quota-grid">{_quota_cards(report)}</div></section>'
        )

    return f"""<!doctype html>
<!--
type: report
slug: harness-usage-audit
schema_version: {comment_value(report.get("schema_version", "unknown"))}
generated_at: {comment_value(report.get("generated_at", "unknown"))}
-->
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
  <title>Harness usage audit</title>
  <style>
    :root {{
      --bg: #071018; --panel: #0d1823; --panel-2: #122231; --text: #eef7ff;
      --muted: #91a6b8; --line: #20384b; --blue: #36a3ff; --cyan: #4ddfd0;
      --violet: #9e83ff; --amber: #f1b84b; --rose: #f0718b; --green: #55d68b;
      --shadow: 0 18px 50px rgba(0, 0, 0, .22); --radius: 20px;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; min-width: 320px; background:
      radial-gradient(circle at 15% -10%, rgba(54,163,255,.18), transparent 34rem),
      radial-gradient(circle at 90% 8%, rgba(158,131,255,.12), transparent 30rem), var(--bg);
      color: var(--text); font: 15px/1.55 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ width: min(1180px, calc(100% - 32px)); margin: 0 auto; padding: 52px 0 72px; }}
    header {{ padding: 34px; border: 1px solid var(--line); border-radius: 28px; background: linear-gradient(145deg, rgba(18,34,49,.94), rgba(9,21,31,.96)); box-shadow: var(--shadow); }}
    h1, h2, h3, p {{ margin-top: 0; }}
    h1 {{ max-width: 720px; margin-bottom: 12px; font-size: clamp(2.2rem, 6vw, 4.6rem); line-height: .98; letter-spacing: -.055em; }}
    h2 {{ margin-bottom: 4px; font-size: clamp(1.45rem, 3vw, 2rem); letter-spacing: -.025em; }}
    h3 {{ margin-bottom: 8px; font-size: 1rem; }}
    .lede {{ max-width: 760px; color: var(--muted); font-size: 1.05rem; }}
    .eyebrow {{ margin-bottom: 8px; color: var(--cyan); font-size: .72rem; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 24px; }}
    .chip, .provider {{ display: inline-flex; align-items: center; border: 1px solid var(--line); border-radius: 999px; background: rgba(77,223,208,.06); color: var(--cyan); font-size: .78rem; font-weight: 750; padding: 5px 10px; }}
    section {{ margin-top: 48px; }}
    .section-heading {{ display: flex; align-items: end; justify-content: space-between; gap: 20px; margin-bottom: 16px; }}
    .section-heading > p {{ max-width: 540px; margin-bottom: 3px; color: var(--muted); text-align: right; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-top: 24px; }}
    .metric, .quota-card, .opportunity, .panel {{ border: 1px solid var(--line); border-radius: var(--radius); background: rgba(13,24,35,.9); box-shadow: var(--shadow); }}
    .metric {{ min-height: 158px; padding: 22px; }}
    .metric-value {{ margin-bottom: 5px; font-size: clamp(1.65rem, 3vw, 2.35rem); font-weight: 780; letter-spacing: -.04em; font-variant-numeric: tabular-nums; }}
    .metric-note, .muted {{ margin: 0; color: var(--muted); font-size: .83rem; }}
    .panel {{ padding: 24px; }}
    .composition-bar {{ display: flex; width: 100%; height: 18px; overflow: hidden; border: 1px solid var(--line); border-radius: 999px; background: #172531; }}
    .segment {{ min-width: 2px; }} .input {{ background: var(--blue); }} .cache {{ background: var(--cyan); }}
    .write {{ background: var(--amber); }} .write-long {{ background: #dd864f; }} .output {{ background: var(--violet); }}
    .reasoning {{ background: var(--rose); }} .tool {{ background: var(--green); }} .empty {{ background: var(--line); }}
    .legend {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px 20px; margin: 20px 0 0; padding: 0; list-style: none; }}
    .legend li {{ display: grid; grid-template-columns: 9px 1fr auto; align-items: center; gap: 8px; color: var(--muted); }}
    .legend strong {{ color: var(--text); font-size: .82rem; font-variant-numeric: tabular-nums; }}
    .swatch {{ width: 9px; height: 9px; border-radius: 3px; }}
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--line); border-radius: var(--radius); background: rgba(13,24,35,.84); }}
    table {{ width: 100%; border-collapse: collapse; min-width: 720px; }}
    .sr-only {{ position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }}
    th, td {{ padding: 14px 16px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: middle; }}
    th {{ color: var(--muted); font-size: .72rem; letter-spacing: .08em; text-transform: uppercase; }}
    tbody tr:last-child td {{ border-bottom: 0; }} .number {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .share-track, .quota-track {{ height: 7px; overflow: hidden; border-radius: 999px; background: #1b2d3c; }}
    .quota-track.unavailable {{ background: repeating-linear-gradient(135deg, #1b2d3c 0 6px, #294154 6px 12px); }}
    .share-track {{ display: inline-block; width: 90px; margin-right: 8px; vertical-align: middle; }}
    .share-track span, .quota-track span {{ display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--blue), var(--cyan)); }}
    small {{ color: var(--muted); }}
    .quota-grid, .opportunity-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; }}
    .quota-card, .opportunity {{ padding: 22px; }}
    .quota-card {{ display: grid; gap: 14px; }} .quota-value {{ margin: 0; font-size: 1.7rem; font-weight: 780; font-variant-numeric: tabular-nums; }}
    .quota-value span {{ color: var(--muted); font-size: .78rem; font-weight: 600; }}
    .opportunity {{ border-left: 3px solid var(--blue); }} .opportunity.cache {{ border-left-color: var(--cyan); }}
    .opportunity.quality, .opportunity.quota {{ border-left-color: var(--amber); }} .evidence {{ color: var(--text); font-weight: 680; }}
    .opportunity p:last-child {{ margin-bottom: 0; color: var(--muted); }}
    .insights {{ margin: 0; padding-left: 20px; }} .insights li {{ padding: 6px 0; }}
    .diagnostic-grid {{ display: grid; grid-template-columns: 1.4fr 1fr; gap: 14px; }}
    .facts {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }}
    .facts span {{ padding: 8px 11px; border: 1px solid var(--line); border-radius: 999px; color: var(--muted); background: rgba(13,24,35,.84); font-size: .78rem; }}
    .facts strong {{ color: var(--text); font-variant-numeric: tabular-nums; }}
    .warnings {{ padding: 22px; border: 1px solid var(--line); border-radius: var(--radius); background: rgba(13,24,35,.84); }}
    .warnings ul {{ margin: 0; padding-left: 18px; color: var(--muted); }}
    .empty-state {{ padding: 24px; border: 1px dashed var(--line); border-radius: var(--radius); color: var(--muted); text-align: center; }}
    footer {{ margin-top: 54px; padding-top: 20px; border-top: 1px solid var(--line); color: var(--muted); font-size: .82rem; }}
    @media (max-width: 860px) {{ .metrics {{ grid-template-columns: repeat(2, 1fr); }} .legend {{ grid-template-columns: repeat(2, 1fr); }} .diagnostic-grid {{ grid-template-columns: 1fr; }} }}
    @media (max-width: 620px) {{ main {{ width: min(100% - 20px, 1180px); padding-top: 20px; }} header {{ padding: 24px; }} .metrics, .quota-grid, .opportunity-grid {{ grid-template-columns: 1fr; }} .section-heading {{ display: block; }} .section-heading > p {{ text-align: left; }} }}
    @media print {{ :root {{ --bg:#fff; --panel:#fff; --panel-2:#fff; --text:#111827; --muted:#4b5563; --line:#d1d5db; }} body {{ background:#fff; }} main {{ width:100%; padding:0; }} header, .metric, .quota-card, .opportunity, .panel {{ box-shadow:none; break-inside:avoid; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <p class="eyebrow">Local agent economy · privacy-safe receipt</p>
    <h1>Harness usage audit</h1>
    <p class="lede">Trace usage, API-equivalent estimates, provider-reported cost, and quota status remain separate measurements.</p>
    <div class="chips">{provider_chips}</div>
    <div class="metrics">
      {_metric("Total tokens", format_tokens(overall.get("total_tokens")), f'{int(overall.get("events") or 0):,} normalized events')}
      {_metric("Estimated API cost", cost, cost_note)}
      {_metric("Pricing coverage", coverage, f'Rate snapshot {pricing.get("as_of", "unknown")}')}
      {_metric("Selected window", window_value, f'Since {str(report.get("since", "unknown")).split("T", 1)[0]} · local calendar days')}
    </div>
  </header>

  <section>
    <div class="section-heading"><div><p class="eyebrow">Composition</p><h2>Where the tokens went</h2></div><p>Disjoint normalized components; cache subsets are removed before aggregation.</p></div>
    <div class="panel">{_token_composition(overall)}</div>
  </section>

{provider_cost_section}

  <section>
    <div class="section-heading"><div><p class="eyebrow">Concentration</p><h2>Usage by model</h2></div><p>Descending by token volume. Unknown pricing stays unknown, never zero.</p></div>
    {_model_rows(report)}
  </section>

{quota_section}

  <section>
    <div class="section-heading"><div><p class="eyebrow">Review queue</p><h2>Improvement opportunities</h2></div><p>Rule-based signals tied to visible evidence. Validate workload context before acting.</p></div>
    <div class="opportunity-grid">{_opportunity_cards(report)}</div>
  </section>

  <section>
    <div class="section-heading"><div><p class="eyebrow">Observations</p><h2>Insights</h2></div><p>Deterministic accounting observations, not productivity or quality judgments.</p></div>
    <div class="panel"><ul class="insights">{_insight_items(report)}</ul></div>
  </section>

  <section>
    <div class="section-heading"><div><p class="eyebrow">Confidence</p><h2>Data quality and backends</h2></div><p>Warnings that can change the headline belong beside the headline.</p></div>
    {_diagnostics(report)}
  </section>

  <footer>
    <p>Generated {escaped(report.get("generated_at", "unknown"))} · Schema v{escaped(report.get("schema_version", "unknown"))} · Pricing source: {escaped(pricing.get("source", "unknown"))}</p>
    <p>{escaped(report.get("cost_semantics", ""))}</p>
  </footer>
</main>
</body>
</html>
"""
