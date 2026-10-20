"""Render the payload as a single self-contained HTML deck.

Design follows the grammar the format established, for reasons the sources
give explicitly:

* **one stat per full-screen card** — dilution is the failure mode; fewer,
  bigger numbers get screenshotted
* **typography as the cinematic device** — type fitted to the viewport, not
  laid out in a dashboard grid
* **colour derived from the data** — the aura's two channels drive every
  accent in the deck, so two different corpora produce different decks
* **per-element motion** — each shape gets its own easing and delay rather
  than one global fade, which is what made the monograms feel individual

Nothing is fetched at runtime: no CDN, no webfont, no script tag with a src.
The deck is one file that works from a thumb drive with the network off.

The renderer reads only the payload.  It never touches the corpus, so a deck
can be restyled and rebuilt without re-scanning twenty gigabytes.
"""

from __future__ import annotations

import html
import json
from string import Template
from typing import Any, Callable

WEEKDAY_ORDER = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _num(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:,.1f}" if value % 1 else f"{int(value):,}"
    return f"{value:,}"


def _big(value: Any) -> str:
    """Abbreviate very large counts so the type can stay huge."""
    if not isinstance(value, (int, float)):
        return "—"
    value = float(value)
    for limit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= limit:
            trimmed = value / limit
            text = f"{trimmed:.1f}".rstrip("0").rstrip(".")
            return f"{text}{suffix}"
    return f"{int(value):,}"


def _get(payload: dict, *path: str, default: Any = None) -> Any:
    node: Any = payload
    for key in path:
        if not isinstance(node, dict):
            return default
        node = node.get(key)
        if node is None:
            return default
    return node


# --------------------------------------------------------------------------
# Card fragments
# --------------------------------------------------------------------------


def _card(act: str, body: str, *, kind: str = "") -> str:
    classes = f"card {kind}".strip()
    return f'<section class="{classes}"><span class="act">{_e(act)}</span>{body}</section>'


def _stat(value: str, label: str, *, sub: str = "", raw: Any = None) -> str:
    attr = f' data-count="{raw}"' if isinstance(raw, (int, float)) else ""
    sub_html = f'<p class="sub">{sub}</p>' if sub else ""
    return (
        f'<p class="stat"{attr}>{value}</p>'
        f'<p class="label">{_e(label)}</p>{sub_html}'
    )


def _ranked_list(rows: list[dict], *, limit: int = 5, unit: str = "") -> str:
    if not rows:
        return ""
    top = rows[:limit]
    peak = max((r.get("count") or 0) for r in top) or 1
    items = []
    for index, row in enumerate(top, start=1):
        width = round(100 * (row.get("count") or 0) / peak, 2)
        name = row.get("name") or "—"
        items.append(
            f'<li style="--i:{index}">'
            f'<span class="rank">{index}</span>'
            f'<span class="name" title="{_e(name)}">{_e(name)}</span>'
            f'<span class="bar"><i style="--w:{width}%"></i></span>'
            f'<span class="count">{_num(row.get("count"))}{_e(unit)}</span>'
            f"</li>"
        )
    return f'<ol class="ranked">{"".join(items)}</ol>'


def _clock(by_hour: list[int]) -> str:
    """A 24-hour radial histogram. Each spoke is one hour of the day."""
    peak = max(by_hour) or 1
    spokes = []
    for hour, count in enumerate(by_hour):
        angle = hour * 15 - 90  # 360/24, midnight at the top
        length = 18 + 74 * (count / peak)
        spokes.append(
            f'<line class="spoke" style="--i:{hour}" x1="0" y1="0" x2="{length:.2f}" y2="0" '
            f'transform="rotate({angle})" stroke-width="{4 if count else 1.5}"/>'
        )
    marks = "".join(
        f'<text class="hmark" x="{104}" y="0" transform="rotate({h * 15 - 90}) '
        f'translate(0,0) rotate({90 - (h * 15 - 90) - 90})">{h:02d}</text>'
        for h in (0, 6, 12, 18)
    )
    return (
        '<svg class="clock" viewBox="-125 -125 250 250" role="img" '
        'aria-label="Activity by hour of day">'
        f'<g>{"".join(spokes)}{marks}</g></svg>'
    )


def _weekday_bars(by_weekday: dict[str, int]) -> str:
    peak = max(by_weekday.values()) if by_weekday else 1
    peak = peak or 1
    bars = []
    for index, day in enumerate(WEEKDAY_ORDER):
        count = by_weekday.get(day, 0)
        height = round(100 * count / peak, 2)
        bars.append(
            f'<li style="--i:{index}"><span class="col"><i style="--h:{height}%"></i></span>'
            f'<span class="day">{day[:3]}</span></li>'
        )
    return f'<ul class="bars">{"".join(bars)}</ul>'


def _months(by_month: dict[str, int]) -> str:
    if not by_month:
        return ""
    peak = max(by_month.values()) or 1
    cells = []
    for index, (month, count) in enumerate(sorted(by_month.items())):
        height = round(100 * count / peak, 2)
        cells.append(
            f'<li style="--i:{index}"><span class="col"><i style="--h:{height}%"></i></span>'
            f'<span class="day">{_e(month[5:])}</span></li>'
        )
    return f'<ul class="bars months">{"".join(cells)}</ul>'


# --------------------------------------------------------------------------
# Cards. Each returns "" when its data is absent, and is then dropped.
# --------------------------------------------------------------------------


def card_cover(p: dict) -> str:
    window = p.get("window") or {}
    honesty = p.get("honesty") or {}
    first, last = window.get("observed_first"), window.get("observed_last")
    span = ""
    if first and last:
        span = f"{first[:10]} — {last[:10]}"
    days = honesty.get("observed_days")
    caveat = ""
    if days and not honesty.get("covers_full_year"):
        caveat = (
            f'<p class="caveat">{days} days of evidence, not a full year. '
            "Every number below covers exactly that span.</p>"
        )
    return _card(
        "",
        '<div class="monogram" aria-hidden="true">'
        '<span class="shape s1"></span><span class="shape s2"></span>'
        '<span class="shape s3"></span></div>'
        '<h1 class="title">Your<br>Year<br>in AI</h1>'
        f'<p class="span">{_e(span)}</p>{caveat}'
        '<p class="scroll-hint">scroll<span class="chev"></span></p>',
        kind="cover",
    )


def card_scale(p: dict) -> str:
    totals = p.get("totals") or {}
    sessions = totals.get("sessions") or 0
    if not sessions:
        return ""
    minutes = totals.get("active_minutes") or 0
    hours = round(minutes / 60)
    return _card(
        "the scale of it",
        _stat(_num(sessions), "conversations", raw=sessions)
        + '<div class="pair">'
        + f'<div><b>{_num(hours)}</b><span>hours of focused work</span></div>'
        + f'<div><b>{_num(totals.get("user_messages"))}</b><span>things you asked</span></div>'
        + "</div>"
        + '<p class="fineprint">Active time counts the gaps between turns and throws away '
        "anything over 30 minutes — a session left open overnight is not eight hours of work.</p>",
    )


def card_tokens(p: dict) -> str:
    tokens = _get(p, "totals", "tokens")
    if not tokens:
        return ""
    total = sum(v for v in tokens.values() if isinstance(v, int))
    if not total:
        return ""
    words = int(total * 0.75)
    return _card(
        "the reading",
        _stat(_big(total), "tokens moved through the models")
        + f'<p class="sub">About {_big(words)} words — read, written and re-read on your behalf.</p>'
        + '<div class="pair small">'
        + f'<div><b>{_big(tokens.get("output", 0))}</b><span>generated for you</span></div>'
        + f'<div><b>{_big(tokens.get("cache_read", 0))}</b><span>context re-read</span></div>'
        + "</div>",
    )


def _ranking_card(p: dict, key: str, act: str, headline: str, empty_ok: bool = False) -> str:
    rows = _get(p, "rankings", key) or []
    if not rows:
        return ""
    top = rows[0]
    return _card(
        act,
        f'<p class="kicker">{_e(headline)}</p>'
        f'<p class="hero">{_e(top.get("name") or "—")}</p>'
        f'<p class="sub">{_num(top.get("count"))} times · '
        f'{round((top.get("share") or 0) * 100)}% of the total</p>'
        + _ranked_list(rows),
    )


def card_tools(p: dict) -> str:
    return _ranking_card(p, "tools", "your top artists", "The tool you reached for most")


def card_skills(p: dict) -> str:
    return _ranking_card(p, "skills", "your genres", "The skill you leaned on most")


def card_models(p: dict) -> str:
    rows = _get(p, "rankings", "models") or []
    if not rows:
        return ""
    top = rows[0]
    return _card(
        "your number one",
        '<p class="kicker">You spent this year with</p>'
        f'<p class="hero model">{_e(top.get("name"))}</p>'
        f'<p class="sub">{_num(top.get("count"))} replies · '
        f'{round((top.get("share") or 0) * 100)}% of everything said back to you</p>'
        + _ranked_list(rows, limit=4),
    )


def card_projects(p: dict) -> str:
    return _ranking_card(p, "projects", "on repeat", "Where the work actually happened")


def card_clock(p: dict) -> str:
    by_hour = _get(p, "rhythm", "by_hour") or []
    if not by_hour or not sum(by_hour):
        return ""
    busiest = _get(p, "rhythm", "busiest_hour")
    night = _get(p, "rhythm", "night_share")
    night_line = ""
    if night is not None:
        night_line = (
            f'<p class="sub">{round(night * 100)}% of it happened between midnight and six.</p>'
        )
    return _card(
        "your clock",
        '<p class="kicker">Every hour you worked, laid on a dial</p>'
        + _clock(by_hour)
        + (f'<p class="hero small">{busiest:02d}:00</p><p class="label">your peak hour</p>'
           if busiest is not None else "")
        + night_line,
        kind="wide",
    )


def card_week(p: dict) -> str:
    by_weekday = _get(p, "rhythm", "by_weekday") or {}
    if not by_weekday or not sum(by_weekday.values()):
        return ""
    busiest = _get(p, "rhythm", "busiest_weekday")
    quietest = _get(p, "rhythm", "quietest_weekday")
    line = ""
    if busiest and quietest:
        line = f'<p class="sub">Busiest on <b>{_e(busiest)}</b>. Quietest on <b>{_e(quietest)}</b>.</p>'
    return _card("your week", '<p class="kicker">The shape of your week</p>'
                 + _weekday_bars(by_weekday) + line, kind="wide")


def card_months(p: dict) -> str:
    by_month = _get(p, "rhythm", "by_month") or {}
    if len(by_month) < 2:
        return ""
    return _card(
        "the arc",
        '<p class="kicker">Month by month</p>' + _months(by_month),
        kind="wide",
    )


def card_streak(p: dict) -> str:
    streak = _get(p, "rhythm", "longest_streak")
    active = _get(p, "rhythm", "active_days")
    if not streak or not active:
        return ""
    return _card(
        "the streak",
        _stat(_num(streak.get("days")), "days in a row", raw=streak.get("days"))
        + f'<p class="sub">{_e(streak.get("start"))} → {_e(streak.get("end"))}</p>'
        + f'<p class="sub">You showed up on <b>{_num(active)}</b> separate days.</p>',
    )


def card_aura(p: dict) -> str:
    aura = _get(p, "identity", "aura")
    if not aura:
        return ""
    inputs = aura.get("inputs") or {}
    mean_hour = inputs.get("mean_hour")
    hour_line = ""
    if mean_hour is not None:
        hours = int(mean_hour)
        minutes = int(round((mean_hour - hours) * 60))
        hour_line = f"the centre of your working day sits at {hours:02d}:{minutes:02d}"
    return _card(
        "your aura",
        '<div class="aura" aria-hidden="true"><span></span><span></span></div>'
        f'<p class="hero">{_e(aura.get("name"))}</p>'
        '<p class="sub">The first colour is where your work sat between building, '
        "exploring and delegating. The second is when you did it"
        + (f" — {hour_line}" if hour_line else "")
        + ".</p>"
        f'<p class="fineprint">{_e(aura.get("primary"))} · {_e(aura.get("secondary"))}</p>',
    )


def card_personality(p: dict) -> str:
    personality = _get(p, "identity", "personality")
    if not personality:
        return ""
    axes = "".join(
        f'<li style="--i:{i}"><b>{_e(a.get("letter"))}</b>'
        f'<span class="pole">{_e(a.get("pole"))}</span>'
        f'<span class="measured">{a.get("measured")} vs {a.get("threshold")}</span></li>'
        for i, a in enumerate(personality.get("axes") or [])
    )
    return _card(
        "your type",
        f'<p class="code">{_e(personality.get("code"))}</p>'
        f'<p class="hero">{_e(personality.get("name"))}</p>'
        f'<ul class="axes">{axes}</ul>'
        f'<p class="fineprint">{_e(personality.get("basis"))}</p>',
    )


def card_first_prompt(p: dict) -> str:
    first = _get(p, "moments", "first_prompt")
    if not first:
        return ""
    text = first.get("text")
    if not text:
        if not first.get("text_redacted"):
            return ""
        body = '<p class="quote redacted">[held back in share-safe mode]</p>'
    else:
        body = f'<p class="quote">{_e(text)}</p>'
    return _card(
        "where it started",
        '<p class="kicker">Your first words of the period</p>'
        + body
        + f'<p class="sub">{_e((first.get("at") or "")[:10])}'
        + (f' · {_e(first.get("source"))}' if first.get("source") else "")
        + "</p>",
    )


def card_phrases(p: dict) -> str:
    phrases = _get(p, "moments", "top_phrases") or []
    if not phrases:
        return ""
    coverage = _get(p, "moments", "phrase_coverage") or {}
    note = ""
    if coverage.get("exhausted"):
        note = (
            f'<p class="fineprint">Counted across the first '
            f'{_num(coverage.get("words_scanned"))} words of your prompts, '
            "not all of them.</p>"
        )
    elif coverage.get("prompts_scanned"):
        note = (
            f'<p class="fineprint">Across all {_num(coverage.get("prompts_scanned"))} '
            "prompts you wrote.</p>"
        )
    return _card(
        "things you kept saying",
        f'<p class="kicker">You said this {_num(phrases[0].get("count"))} times</p>'
        f'<p class="hero quote-mark">{_e(phrases[0].get("phrase"))}</p>'
        + _ranked_list(
            [{"name": r["phrase"], "count": r["count"]} for r in phrases], limit=6
        )
        + note,
    )


def card_longest(p: dict) -> str:
    longest = _get(p, "moments", "longest_session")
    if not longest:
        return ""
    minutes = longest.get("active_minutes") or 0
    return _card(
        "the long one",
        _stat(f"{_num(round(minutes / 60, 1))}h", "your longest single session", raw=minutes)
        + f'<p class="sub">{_num(longest.get("messages"))} messages · '
        f'{_num(longest.get("tool_calls"))} tool calls</p>'
        + (f'<p class="sub mono">{_e(longest.get("branch"))}</p>' if longest.get("branch") else "")
        + f'<p class="fineprint">{_e((longest.get("started") or "")[:10])}</p>',
    )


def card_hardest(p: dict) -> str:
    hardest = _get(p, "moments", "hardest_session")
    if not hardest:
        return ""
    return _card(
        "the hard one",
        _stat(_num(hardest.get("tool_calls")), "tool calls in a single session",
              raw=hardest.get("tool_calls"))
        + '<p class="sub">The most work it took to get through one problem.</p>'
        + (f'<p class="sub mono">{_e(hardest.get("branch"))}</p>' if hardest.get("branch") else ""),
    )


def card_outcomes(p: dict) -> str:
    outcomes = p.get("outcomes") or {}
    tiles = []
    git = outcomes.get("git")
    if git and git.get("commits"):
        tiles.append((_num(git["commits"]), "commits landed"))
    kg = outcomes.get("knowledge_graph")
    if kg and kg.get("entities"):
        tiles.append((_num(kg["entities"]), "things you wrote down"))
        if kg.get("edges"):
            tiles.append((_num(kg["edges"]), "connections between them"))
    memory = outcomes.get("memory")
    if memory and memory.get("entities"):
        tiles.append((_num(memory["entities"]), "lessons you taught it"))
    if not tiles:
        return ""
    body = "".join(
        f'<div style="--i:{i}"><b>{value}</b><span>{_e(label)}</span></div>'
        for i, (value, label) in enumerate(tiles)
    )
    return _card(
        "what came of it",
        '<p class="kicker">None of this was just talk</p>'
        f'<div class="tiles">{body}</div>',
        kind="wide",
    )


def card_most_cited(p: dict) -> str:
    memory = _get(p, "outcomes", "memory") or {}
    linked = memory.get("most_linked") or []
    if not linked:
        return ""
    top = linked[0]
    return _card(
        "the lesson that stuck",
        '<p class="kicker">The thing your agent refers back to most</p>'
        f'<p class="hero small">{_e(top.get("title"))}</p>'
        f'<p class="sub">referenced by {_num(top.get("inbound"))} other notes</p>'
        + _ranked_list(
            [{"name": r.get("title"), "count": r.get("inbound")} for r in linked], limit=5
        ),
    )


def card_coverage(p: dict) -> str:
    coverage = p.get("coverage") or []
    if not coverage:
        return ""
    rows = []
    for report in coverage:
        available = report.get("available")
        detail = (
            f'{_num(report.get("records"))} records'
            if available
            else _e(report.get("reason") or "not found")
        )
        span = ""
        if report.get("first") and report.get("last"):
            span = f'{report["first"][:10]} → {report["last"][:10]}'
        rows.append(
            f'<li class="{"on" if available else "off"}">'
            f'<span class="name">{_e(report.get("source"))}</span>'
            f'<span class="detail">{detail}</span>'
            f'<span class="span">{_e(span)}</span></li>'
        )
    honesty = p.get("honesty") or {}
    return _card(
        "what this is built from",
        '<p class="kicker">Receipts</p>'
        f'<ul class="coverage">{"".join(rows)}</ul>'
        f'<p class="fineprint">{_e(honesty.get("no_percentiles", ""))}</p>'
        f'<p class="fineprint">{_e(honesty.get("active_time_method", ""))}</p>',
        kind="wide",
    )


def card_share(p: dict) -> str:
    """A 9:16 panel sized for a phone screenshot, the way the format expects."""
    totals = p.get("totals") or {}
    tools = _get(p, "rankings", "tools") or []
    models = _get(p, "rankings", "models") or []
    personality = _get(p, "identity", "personality") or {}
    aura = _get(p, "identity", "aura") or {}
    window = p.get("window") or {}
    lines = []
    if tools:
        lines.append(("top tool", tools[0].get("name")))
    if models:
        lines.append(("top model", models[0].get("name")))
    if personality:
        lines.append(("type", f'{personality.get("code")} · {personality.get("name")}'))
    if aura:
        lines.append(("aura", aura.get("name")))
    rows = "".join(
        f'<li><span>{_e(label)}</span><b>{_e(value)}</b></li>' for label, value in lines if value
    )
    span = ""
    if window.get("observed_first") and window.get("observed_last"):
        span = f'{window["observed_first"][:10]} — {window["observed_last"][:10]}'
    return _card(
        "for sharing",
        '<div class="sharecard">'
        '<div class="monogram small" aria-hidden="true">'
        '<span class="shape s1"></span><span class="shape s2"></span>'
        '<span class="shape s3"></span></div>'
        "<h2>Your Year in AI</h2>"
        f'<p class="span">{_e(span)}</p>'
        f'<p class="mega">{_num(totals.get("sessions"))}</p><p class="label">conversations</p>'
        f'<ul class="sharelist">{rows}</ul>'
        "<p class=\"mark\">year-in-ai</p>"
        "</div>"
        '<p class="fineprint">Screenshot this one.</p>',
    )


CARDS: tuple[Callable[[dict], str], ...] = (
    card_cover, card_scale, card_tokens, card_tools, card_skills, card_models,
    card_projects, card_clock, card_week, card_months, card_streak, card_aura,
    card_personality, card_first_prompt, card_phrases, card_longest, card_hardest,
    card_outcomes, card_most_cited, card_coverage, card_share,
)


# --------------------------------------------------------------------------
# Deck shell
# --------------------------------------------------------------------------

_SHELL = Template(
    """<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>$title</title>
<meta name="generator" content="year-in-ai $version">
<style>
:root{
  --a1:$aura1; --a2:$aura2;
  --bg:#08070c; --fg:#f6f4ef; --dim:#9a94a8; --line:rgba(246,244,239,.14);
  --ease:cubic-bezier(.22,.71,.24,1);
  --font:ui-sans-serif,-apple-system,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-snap-type:y mandatory;scroll-behavior:smooth;-webkit-text-size-adjust:100%}
body{
  background:var(--bg);color:var(--fg);font-family:var(--font);
  -webkit-font-smoothing:antialiased;overflow-x:hidden;
}
/* A slow aura wash sits behind everything; both stops come from the data. */
body::before{
  content:"";position:fixed;inset:-20%;z-index:0;pointer-events:none;
  background:
    radial-gradient(45% 40% at 18% 12%, color-mix(in oklab,var(--a1),transparent 55%), transparent 70%),
    radial-gradient(50% 45% at 82% 78%, color-mix(in oklab,var(--a2),transparent 60%), transparent 72%);
  filter:blur(40px);animation:drift 34s var(--ease) infinite alternate;
}
@keyframes drift{to{transform:translate3d(0,-4%,0) scale(1.08)}}

.card{
  position:relative;z-index:1;min-height:100svh;scroll-snap-align:start;scroll-snap-stop:always;
  display:flex;flex-direction:column;justify-content:center;align-items:flex-start;
  gap:.7rem;padding:max(6vh,3rem) clamp(1.25rem,7vw,7rem);max-width:min(1100px,100%);
  margin-inline:auto;
}
.card.wide{max-width:min(1280px,100%)}

/* Every element carries its own delay, so nothing arrives as one flat block. */
.card>*{opacity:0;transform:translateY(18px);transition:opacity .7s var(--ease),transform .7s var(--ease)}
.card>*:nth-child(1){transition-delay:.02s} .card>*:nth-child(2){transition-delay:.10s}
.card>*:nth-child(3){transition-delay:.18s} .card>*:nth-child(4){transition-delay:.26s}
.card>*:nth-child(5){transition-delay:.34s} .card>*:nth-child(6){transition-delay:.42s}
.card.in>*{opacity:1;transform:none}

.act{font:600 .72rem/1 var(--mono);letter-spacing:.22em;text-transform:uppercase;color:var(--dim)}
.act:empty{display:none}
.kicker{font-size:clamp(1rem,2.4vw,1.5rem);color:var(--dim);max-width:26ch}
.title{font-size:clamp(3.6rem,15vw,11rem);line-height:.86;letter-spacing:-.045em;font-weight:800}
.stat{font-size:clamp(3.6rem,17vw,13rem);line-height:.82;letter-spacing:-.05em;font-weight:800;
  background:linear-gradient(102deg,var(--fg),var(--a1) 55%,var(--a2));
  -webkit-background-clip:text;background-clip:text;color:transparent;font-variant-numeric:tabular-nums}
.hero{font-size:clamp(2.1rem,7.5vw,5.4rem);line-height:1.02;letter-spacing:-.035em;font-weight:750;
  overflow-wrap:anywhere}
.hero.small{font-size:clamp(1.6rem,4.4vw,3rem)}
.hero.model{font-family:var(--mono);font-size:clamp(1.5rem,5.2vw,3.6rem);letter-spacing:-.02em}
.hero.quote-mark::before{content:"“";color:var(--a1)}
.hero.quote-mark::after{content:"”";color:var(--a1)}
.label{font-size:clamp(1rem,2.6vw,1.6rem);color:var(--dim);letter-spacing:.01em}
.sub{font-size:clamp(.95rem,1.9vw,1.2rem);color:var(--fg);opacity:.82;max-width:44ch}
.sub.mono{font-family:var(--mono);font-size:.9rem;opacity:.6}
.fineprint{font-size:.8rem;color:var(--dim);max-width:52ch;line-height:1.5}
.caveat{font-size:.9rem;color:var(--fg);opacity:.72;max-width:40ch;border-left:2px solid var(--a1);
  padding-left:.8rem}
.span{font-family:var(--mono);font-size:.9rem;color:var(--dim);letter-spacing:.06em}
.quote{font-size:clamp(1.3rem,4vw,2.6rem);line-height:1.24;font-weight:600;max-width:20ch;
  border-left:3px solid var(--a1);padding-left:clamp(.8rem,2vw,1.6rem)}
.quote.redacted{color:var(--dim);font-style:italic;font-weight:400}
.code{font-family:var(--mono);font-size:clamp(3rem,13vw,9rem);font-weight:700;letter-spacing:.06em;
  color:var(--a1)}

.pair{display:flex;flex-wrap:wrap;gap:clamp(1.4rem,5vw,4rem);margin-top:.6rem}
.pair div{display:flex;flex-direction:column}
.pair b{font-size:clamp(1.7rem,5vw,3rem);font-weight:750;font-variant-numeric:tabular-nums}
.pair span{font-size:.9rem;color:var(--dim)}
.pair.small b{font-size:clamp(1.3rem,3.4vw,2.1rem)}

.ranked{list-style:none;width:100%;max-width:640px;margin-top:.5rem}
.ranked li{display:grid;grid-template-columns:1.6rem minmax(6ch,1fr) 3fr auto;gap:.7rem;
  align-items:center;padding:.42rem 0;border-bottom:1px solid var(--line)}
.ranked .rank{font-family:var(--mono);font-size:.78rem;color:var(--dim)}
.ranked .name{font-weight:600;font-size:clamp(.85rem,1.7vw,1.05rem);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;direction:rtl;text-align:left}
.ranked .bar{height:5px;background:var(--line);border-radius:3px;overflow:hidden}
.ranked .bar i{display:block;height:100%;width:0;border-radius:3px;
  background:linear-gradient(90deg,var(--a1),var(--a2));
  transition:width .85s var(--ease);transition-delay:calc(var(--i)*70ms + .2s)}
.card.in .ranked .bar i{width:var(--w)}
.ranked .count{font-family:var(--mono);font-size:.8rem;color:var(--dim);font-variant-numeric:tabular-nums}

.clock{width:min(58vw,340px);height:auto;overflow:visible;margin:.4rem 0}
.clock .spoke{stroke:var(--a1);stroke-linecap:round;opacity:.85;
  transform-box:fill-box;transform-origin:0 0;
  scale:0 1;transition:scale .5s var(--ease);transition-delay:calc(var(--i)*26ms + .15s)}
.card.in .clock .spoke{scale:1 1}
.clock .hmark{fill:var(--dim);font:600 9px var(--mono);text-anchor:middle;dominant-baseline:middle}

.bars{list-style:none;display:flex;align-items:flex-end;gap:clamp(.35rem,1.4vw,1rem);
  height:min(34vh,240px);width:100%;max-width:680px;margin:.6rem 0}
.bars li{flex:1;display:flex;flex-direction:column;justify-content:flex-end;height:100%;gap:.45rem}
.bars .col{flex:1;display:flex;align-items:flex-end}
.bars .col i{display:block;width:100%;height:0;border-radius:5px 5px 2px 2px;
  background:linear-gradient(180deg,var(--a2),var(--a1));
  transition:height .8s var(--ease);transition-delay:calc(var(--i)*55ms + .2s)}
.card.in .bars .col i{height:var(--h)}
.bars .day{font:600 .68rem/1 var(--mono);color:var(--dim);text-align:center;letter-spacing:.04em}
.bars.months .day{font-size:.6rem}

.tiles{display:flex;flex-wrap:wrap;gap:clamp(1.2rem,4vw,3rem)}
.tiles div{display:flex;flex-direction:column;min-width:8rem}
.tiles b{font-size:clamp(1.9rem,6vw,3.6rem);font-weight:780;font-variant-numeric:tabular-nums;
  background:linear-gradient(100deg,var(--fg),var(--a2));-webkit-background-clip:text;
  background-clip:text;color:transparent}
.tiles span{font-size:.85rem;color:var(--dim)}

.axes{list-style:none;display:flex;flex-wrap:wrap;gap:1.4rem;margin:.5rem 0}
.axes li{display:flex;flex-direction:column;gap:.15rem;min-width:9rem;
  border-top:2px solid var(--a1);padding-top:.5rem}
.axes b{font-family:var(--mono);font-size:1.5rem;color:var(--a1)}
.axes .pole{font-size:.95rem;font-weight:600}
.axes .measured{font-family:var(--mono);font-size:.7rem;color:var(--dim)}

.coverage{list-style:none;width:100%;max-width:760px;font-family:var(--mono);font-size:.82rem}
.coverage li{display:grid;grid-template-columns:11rem 1fr auto;gap:1rem;padding:.42rem 0;
  border-bottom:1px solid var(--line);align-items:baseline}
.coverage .name{font-weight:600}
.coverage li.off{color:var(--dim)}
.coverage li.on .name::before{content:"● ";color:var(--a1)}
.coverage li.off .name::before{content:"○ "}
.coverage .span{color:var(--dim);font-size:.72rem}

.aura{position:relative;width:min(52vw,300px);aspect-ratio:1;margin:.4rem 0}
.aura span{position:absolute;inset:0;border-radius:50%;filter:blur(28px);mix-blend-mode:screen}
.aura span:first-child{background:var(--a1);animation:orb 11s var(--ease) infinite alternate}
.aura span:last-child{background:var(--a2);animation:orb 14s var(--ease) infinite alternate-reverse}
@keyframes orb{to{transform:translate(16%,-12%) scale(1.16)}}

/* Three layers, three shapes, three motion languages — the monogram idea. */
.monogram{position:relative;width:min(40vw,190px);aspect-ratio:1}
.monogram.small{width:78px}
.monogram .shape{position:absolute;inset:0;mix-blend-mode:screen}
.monogram .s1{background:var(--a1);border-radius:32%;animation:m1 9s var(--ease) infinite alternate}
.monogram .s2{background:var(--a2);clip-path:polygon(50% 0,100% 50%,50% 100%,0 50%);
  animation:m2 7s linear infinite}
.monogram .s3{border:2px solid var(--fg);border-radius:50%;opacity:.5;
  animation:m3 12s var(--ease) infinite alternate}
@keyframes m1{to{border-radius:48%;transform:rotate(24deg) scale(.9)}}
@keyframes m2{to{transform:rotate(360deg)}}
@keyframes m3{to{transform:scale(.7)}}

.sharecard{width:min(90vw,340px);aspect-ratio:9/16;border-radius:20px;padding:1.6rem 1.4rem;
  display:flex;flex-direction:column;gap:.5rem;justify-content:center;
  background:linear-gradient(155deg,color-mix(in oklab,var(--a1),black 62%),
    color-mix(in oklab,var(--a2),black 74%));border:1px solid var(--line)}
.sharecard h2{font-size:1.7rem;line-height:1;letter-spacing:-.03em}
.sharecard .mega{font-size:4rem;line-height:.9;font-weight:800;font-variant-numeric:tabular-nums}
.sharecard .label{font-size:.8rem}
.sharelist{list-style:none;display:flex;flex-direction:column;gap:.4rem;margin-top:.6rem}
.sharelist li{display:flex;flex-direction:column;border-top:1px solid var(--line);padding-top:.3rem}
.sharelist span{font:600 .6rem/1 var(--mono);letter-spacing:.16em;text-transform:uppercase;
  color:var(--dim)}
.sharelist b{font-size:.95rem;overflow-wrap:anywhere}
.sharecard .mark{margin-top:auto;font:600 .62rem/1 var(--mono);letter-spacing:.2em;
  text-transform:uppercase;color:var(--dim)}

.scroll-hint{font:600 .7rem/1 var(--mono);letter-spacing:.2em;text-transform:uppercase;
  color:var(--dim);display:flex;align-items:center;gap:.5rem}
.chev{width:7px;height:7px;border-right:1.5px solid var(--dim);border-bottom:1.5px solid var(--dim);
  transform:rotate(45deg);animation:nudge 1.8s var(--ease) infinite}
@keyframes nudge{50%{transform:rotate(45deg) translate(3px,3px)}}

.progress{position:fixed;top:0;left:0;height:2px;width:100%;transform-origin:0 50%;z-index:9;
  background:linear-gradient(90deg,var(--a1),var(--a2));transform:scaleX(0)}

@media (prefers-reduced-motion:reduce){
  html{scroll-behavior:auto}
  *,*::before,*::after{animation:none!important;transition:none!important}
  .card>*{opacity:1;transform:none}
  .card.in .ranked .bar i{width:var(--w)}
  .ranked .bar i{width:var(--w)}
  .bars .col i{height:var(--h)}
  .clock .spoke{scale:1 1}
}
@media print{
  html{scroll-snap-type:none}
  .card{min-height:auto;page-break-after:always;padding:2rem}
  .card>*{opacity:1;transform:none}
}
</style>
</head>
<body>
<div class="progress" id="progress"></div>
$cards
<script>
(function(){
  var cards=[].slice.call(document.querySelectorAll('.card'));
  var reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Reveal on entry. Cards stay revealed once seen, so scrolling back up
  // does not replay every animation.
  if('IntersectionObserver' in window && !reduce){
    var io=new IntersectionObserver(function(entries){
      entries.forEach(function(e){ if(e.isIntersecting){ e.target.classList.add('in'); countUp(e.target); } });
    },{threshold:.35});
    cards.forEach(function(c){io.observe(c)});
  } else {
    cards.forEach(function(c){c.classList.add('in')});
  }

  // Numbers count toward their value rather than appearing at it.
  function countUp(card){
    var el=card.querySelector('.stat[data-count]');
    if(!el || el.dataset.done) return;
    el.dataset.done='1';
    var target=parseFloat(el.dataset.count), label=el.textContent, dur=900, t0=null;
    if(!isFinite(target)||target<=0) return;
    var suffix=label.replace(/[0-9.,]/g,'');
    function frame(t){
      if(t0===null)t0=t;
      var k=Math.min(1,(t-t0)/dur), eased=1-Math.pow(1-k,3);
      var v=target*eased;
      el.textContent=(v>=1000?Math.round(v).toLocaleString():v.toFixed(1))+suffix;
      if(k<1)requestAnimationFrame(frame); else el.textContent=label;
    }
    requestAnimationFrame(frame);
  }

  var bar=document.getElementById('progress');
  addEventListener('scroll',function(){
    var h=document.documentElement.scrollHeight-innerHeight;
    bar.style.transform='scaleX('+(h>0?scrollY/h:0)+')';
  },{passive:true});

  addEventListener('keydown',function(e){
    var i=cards.findIndex(function(c){return c.getBoundingClientRect().top>=-2});
    if(e.key==='ArrowDown'||e.key===' '){e.preventDefault();(cards[i+ (cards[i]&&cards[i].getBoundingClientRect().top<2?1:0)]||cards[cards.length-1]).scrollIntoView();}
    if(e.key==='ArrowUp'){e.preventDefault();(cards[Math.max(0,i-1)]||cards[0]).scrollIntoView();}
  });
})();
</script>
</body>
</html>
"""
)


def render_deck(payload: dict) -> str:
    """Render the payload into one self-contained HTML document."""
    aura = _get(payload, "identity", "aura") or {}
    cards = [fragment for card in CARDS if (fragment := card(payload))]
    window = payload.get("window") or {}
    title = f"Your Year in AI — {window.get('label', 'all time')}"
    return _SHELL.substitute(
        title=_e(title),
        version=_e(payload.get("generator_version", "")),
        aura1=aura.get("primary", "#6c7cff"),
        aura2=aura.get("secondary", "#f0a6c0"),
        cards="\n".join(cards),
    )
