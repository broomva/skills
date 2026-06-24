"""Swapit static report — a self-contained, generatively-authored HTML artifact.

Per the workspace P18 (Format-Follows-Audience) discipline, a human-read artifact where
presentation carries knowledge is authored as rich, self-contained Category-C HTML: inline
CSS, inline SVG (band donut + per-item risk bars), no external dependencies, dark-mode aware.

The interactive *live* dashboard (``swapit serve``) ships in M2; this is the shareable
snapshot — open it in a browser, send it to a partner, print it.
"""
from __future__ import annotations

import html
import time

BANDS = ("high", "medium", "low")
BAND_COLOR = {"high": "#e5484d", "medium": "#f5a524", "low": "#30a46c"}


def household_summary(rows: list[dict]) -> dict:
    total = len(rows)
    bands = {"high": 0, "medium": 0, "low": 0}
    addressed = 0
    reduction_available = 0
    for r in rows:
        band = r["assessment"]["risk"]["band"]
        bands[band] = bands.get(band, 0) + 1
        status = r["item"].get("status")
        if status in ("swapped", "disposed", "keep"):
            addressed += 1  # keep = a deliberate "decided it's fine" decision
        elif r["best_swap"]:
            reduction_available += round(
                r["assessment"]["risk"]["score"] * r["best_swap"]["pct"] / 100
            )
    return {
        "total": total,
        "bands": bands,
        "addressed": addressed,
        "reduction_available": reduction_available,
    }


def _esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def _donut(bands: dict, total: int) -> str:
    """Inline SVG donut of the band distribution."""
    if total == 0:
        return '<div class="muted">No items yet.</div>'
    radius, circ = 52, 2 * 3.14159 * 52
    offset = 0.0
    segments = []
    for band in BANDS:
        n = bands.get(band, 0)
        if not n:
            continue
        frac = n / total
        dash = frac * circ
        segments.append(
            f'<circle cx="60" cy="60" r="{radius}" fill="none" stroke="{BAND_COLOR[band]}" '
            f'stroke-width="16" stroke-dasharray="{dash:.2f} {circ - dash:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 60 60)"/>'
        )
        offset += dash
    return (
        f'<svg viewBox="0 0 120 120" width="120" height="120" role="img" aria-label="risk distribution">'
        f'{"".join(segments)}'
        f'<text x="60" y="56" text-anchor="middle" class="donut-num">{total}</text>'
        f'<text x="60" y="74" text-anchor="middle" class="donut-lbl">items</text>'
        f"</svg>"
    )


def _risk_bar(score: int, band: str) -> str:
    return (
        f'<span class="bar"><span class="bar-fill" style="width:{min(100, score)}%;'
        f'background:{BAND_COLOR[band]}"></span></span>'
    )


def _swap_rows(rows: list[dict]) -> str:
    actionable = [r for r in rows if r["item"].get("status") not in ("swapped", "disposed", "keep")]
    actionable.sort(key=lambda r: r["assessment"]["risk"]["score"], reverse=True)
    out = []
    for r in actionable:
        item = r["item"]
        rr = r["assessment"]["risk"]
        best = r["best_swap"]
        hazards = ", ".join(
            _esc(c["name"]) for c in rr["contributions"][:3] if c["risk"] > 0
        ) or "<span class='muted'>—</span>"
        swap_cell = (
            f'<strong>{_esc(best["name"])}</strong> <span class="pct">−{best["pct"]}%</span>'
            if best
            else '<span class="muted">assess for options</span>'
        )
        out.append(
            f"<tr>"
            f'<td class="score"><span class="dot" style="background:{BAND_COLOR[rr["band"]]}"></span>{rr["score"]}{_risk_bar(rr["score"], rr["band"])}</td>'
            f"<td><strong>{_esc(item['name'])}</strong><br><span class='muted'>{_esc(item.get('room') or '—')} · {_esc(item.get('status') or '—')}</span></td>"
            f"<td>{hazards}</td>"
            f"<td>{swap_cell}</td>"
            f"</tr>"
        )
    if not out:
        return '<tr><td colspan="4" class="muted">Nothing flagged for swapping. Add items with <code>swapit add</code>.</td></tr>'
    return "".join(out)


def _room_cards(rows: list[dict]) -> str:
    by_room: dict[str, list[dict]] = {}
    for r in rows:
        by_room.setdefault(r["item"].get("room") or "unassigned", []).append(r)
    cards = []
    for room, rs in sorted(by_room.items(), key=lambda kv: -max((x["assessment"]["risk"]["score"] for x in kv[1]), default=0)):
        top = max(rs, key=lambda x: x["assessment"]["risk"]["score"])
        band = top["assessment"]["risk"]["band"]
        cards.append(
            f'<div class="room-card" style="border-left:4px solid {BAND_COLOR[band]}">'
            f"<div class='room-name'>{_esc(room)}</div>"
            f"<div class='room-meta'>{len(rs)} item{'s' if len(rs) != 1 else ''} · worst {top['assessment']['risk']['score']}</div>"
            f"</div>"
        )
    return "".join(cards) or '<div class="muted">No rooms with items yet.</div>'


CSS = """
:root{--bg:#fbfbfd;--card:#fff;--fg:#1a1a22;--muted:#6b7280;--line:#e6e6ee;--accent:#3b5fc4}
@media(prefers-color-scheme:dark){:root{--bg:#0f1117;--card:#171a23;--fg:#e8e8f0;--muted:#9aa0ad;--line:#262a36;--accent:#8aa9ff}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:32px 20px 80px}
h1{font-size:26px;margin:0 0 4px}.sub{color:var(--muted);margin:0 0 28px}
.cards{display:grid;grid-template-columns:auto repeat(3,1fr);gap:14px;align-items:center;margin-bottom:32px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
.card .n{font-size:30px;font-weight:700;line-height:1}.card .l{color:var(--muted);font-size:13px;margin-top:4px}
.donut-wrap{display:flex;justify-content:center}
.donut-num{font-size:26px;font-weight:700;fill:var(--fg)}.donut-lbl{font-size:11px;fill:var(--muted)}
h2{font-size:18px;margin:34px 0 14px;border-bottom:1px solid var(--line);padding-bottom:8px}
.rooms{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px}
.room-card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.room-name{font-weight:600;text-transform:capitalize}.room-meta{color:var(--muted);font-size:13px;margin-top:2px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}
th,td{text-align:left;padding:12px 14px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
tr:last-child td{border-bottom:none}
.score{white-space:nowrap;font-weight:700;min-width:120px}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:middle}
.bar{display:block;height:5px;background:var(--line);border-radius:3px;margin-top:6px;overflow:hidden}
.bar-fill{display:block;height:100%}
.pct{color:var(--accent);font-weight:600}.muted{color:var(--muted)}
code{background:rgba(127,127,127,.14);padding:1px 5px;border-radius:5px;font-size:.9em}
footer{margin-top:40px;color:var(--muted);font-size:12px;text-align:center}
"""


def render_report(rows: list[dict], kn) -> str:
    s = household_summary(rows)
    ks = kn.stats()
    generated = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    pct_addressed = round(100 * s["addressed"] / s["total"]) if s["total"] else 0
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Swapit — household exposure report</title>
<style>{CSS}</style></head>
<body><div class="wrap">
<h1>🧪 Swapit household report</h1>
<p class="sub">Generated {generated} · {ks['hazards']} hazards · {ks['item_classes']} item-classes · {ks['alternatives']} alternatives in the knowledge graph</p>

<div class="cards">
  <div class="donut-wrap">{_donut(s['bands'], s['total'])}</div>
  <div class="card"><div class="n" style="color:{BAND_COLOR['high']}">{s['bands']['high']}</div><div class="l">high risk 🔴</div></div>
  <div class="card"><div class="n">{pct_addressed}%</div><div class="l">addressed ({s['addressed']}/{s['total']})</div></div>
  <div class="card"><div class="n">{s['reduction_available']}</div><div class="l">exposure pts reducible</div></div>
</div>

<h2>By room</h2>
<div class="rooms">{_room_cards(rows)}</div>

<h2>Swap these first</h2>
<table>
<thead><tr><th>Risk</th><th>Item</th><th>Carries</th><th>Best swap</th></tr></thead>
<tbody>{_swap_rows(rows)}</tbody>
</table>

<footer>swapit · local-first household toxics inventory · the agent is the app<br>
Risk = severity × presence × evidence × exposure × frequency × condition. Prioritize the top of the list.</footer>
</div></body></html>"""
