"""Words you wrote and words you read, folded from the ledger.

**Written** counts prompts a person wrote. A prompt counts when:

1. its store says a person wrote it (``author == "human"``), or its store
   records no author (``unknown``) and it comes from a text-only source
   (bridged markdown, exports) that has passed the filters below;
2. it is not scripted: no automation marker, its exact text does not recur in
   three or more sessions (150+ characters), and its opening does not recur in
   four or more sessions (40+ characters);
3. it is not a duplicate of the same text already counted from a
   higher-priority store within 36 hours (20 minutes for short prompts).

Filter 2 is skipped for stores with an exact author flag (T3): a person may
paste the same brief into several threads, and the store has already said who
wrote it.

**Read** counts the final reply to each counted prompt, times a read share.
The share is an assumption the reader states, not a measurement; the default
band is 60-70%. Prompts from stores that never kept replies (prompt histories)
get an estimated reply: the month's measured mean if it has 500 or more
replies, else the pooled mean. Estimated words are reported separately.

Replies to agent-written prompts are reported as the agents' own volume and
excluded from what was read.
"""

from __future__ import annotations

import collections
import datetime as _dt
import statistics
from typing import Dict, Iterable, List, Optional

#: Dedupe priority: the first store to claim a prompt keeps it.
PRIORITY = ("t3", "claude_code", "conductor", "codex", "gemini", "claude_history", "export", "bridged",
            "codex_history")
#: Stores whose author flag is exact; scripted-prompt filters do not apply.
EXACT_AUTHOR = {"t3"}
#: Stores with no author flag whose ``unknown`` prompts may count after filtering.
TEXT_ONLY = {"bridged", "export"}
#: Stores that keep prompts but never replies.
NO_REPLIES = {"claude_history", "codex_history"}
#: Unflagged prompts longer than this are dispatched briefs far more often than writing.
UNFLAGGED_MAX_CHARS = 1500


def _month(ts: float, zone: _dt.tzinfo) -> str:
    return _dt.datetime.fromtimestamp(ts, zone).strftime("%Y-%m")


def _rank(src: str) -> int:
    return PRIORITY.index(src) if src in PRIORITY else len(PRIORITY)


def fold(rows: Iterable[dict], read_share=(0.60, 0.65, 0.70), utc_offset_hours: float = -5.0,
         text_only_until: Optional[float] = None) -> dict:
    """Fold ledger rows into the written/read summary.

    ``text_only_until``: ignore text-only sources from this time on. Use it once
    a store with exact authors covers the period: measured on 2026-10-18 to
    2026-11-13, only ~18% of bridged prompts matched a human-typed T3 prompt.
    """
    zone = _dt.timezone(_dt.timedelta(hours=utc_offset_hours))
    rows = list(rows)
    prompts = [r for r in rows if r["kind"] == "prompt"]

    sessions_by_text: Dict[str, set] = collections.defaultdict(set)
    sessions_by_open: Dict[str, set] = collections.defaultdict(set)
    for r in prompts:
        if r["chars"] >= 150:
            sessions_by_text[r["h"]].add(r["sess"])
        if r.get("ph"):
            sessions_by_open[r["ph"]].add(r["sess"])
    repeated_text = {h for h, s in sessions_by_text.items() if len(s) >= 3}
    repeated_open = {h for h, s in sessions_by_open.items() if len(s) >= 4}

    dropped: Dict[str, int] = collections.Counter()

    def counts_as_written(r: dict) -> bool:
        src = r["src"]
        if text_only_until is not None and src in TEXT_ONLY and r["ts"] >= text_only_until:
            dropped["text-only after exact coverage"] += 1
            return False
        if r["author"] == "agent":
            dropped["agent author"] += 1
            return False
        if r["author"] == "unknown" and src not in TEXT_ONLY:
            dropped["unknown author"] += 1
            return False
        if src not in EXACT_AUTHOR:
            if "marker" in r.get("flags", ()):
                dropped["automation marker"] += 1
                return False
            if r["h"] in repeated_text:
                dropped["repeated text"] += 1
                return False
            if r.get("ph") in repeated_open:
                dropped["repeated opening"] += 1
                return False
            if src in TEXT_ONLY and r["chars"] > UNFLAGGED_MAX_CHARS:
                dropped["long unflagged"] += 1
                return False
        return True

    human_ids = {r["id"] for r in prompts if counts_as_written(r)}

    # Cross-store dedupe of prompts and of replies, by content hash and time.
    def dedupe(items: List[dict], label: str) -> List[dict]:
        items.sort(key=lambda r: (_rank(r["src"]), r["ts"]))
        seen: Dict[str, List[tuple]] = collections.defaultdict(list)
        kept = []
        for r in items:
            window = 36 * 3600 if (r["chars"] >= 80 or r["src"] == "export") else 20 * 60
            duplicate = False
            for ts, src in seen[r["h"]]:
                w = 36 * 3600 if "export" in (src, r["src"]) else window
                if abs(ts - r["ts"]) <= w:
                    duplicate = True
                    break
            if duplicate:
                dropped[f"duplicate {label}"] += 1
                continue
            seen[r["h"]].append((r["ts"], r["src"]))
            kept.append(r)
        return kept

    written = dedupe([r for r in prompts if r["id"] in human_ids], "prompt")
    replies = [r for r in rows if r["kind"] == "reply"]
    human_replies = dedupe([r for r in replies if r.get("turn") in human_ids], "reply")
    agent_replies = dedupe([r for r in replies if r.get("turn") not in human_ids], "agent reply")

    months: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for r in written:
        m = months[_month(r["ts"], zone)]
        m["prompts"] += 1
        m["words_written"] += r["words"]
        m["authored_words"] += r.get("authored_words", r["words"])
        if r["src"] in NO_REPLIES:
            m["prompts_without_reply"] += 1
    for r in human_replies:
        m = months[_month(r["ts"], zone)]
        m["replies"] += 1
        m["reply_words"] += r["words"]
    for r in agent_replies:
        m = months[_month(r["ts"], zone)]
        m["agent_replies"] += 1
        m["agent_reply_words"] += r["words"]

    total_replies = sum(m["replies"] for m in months.values())
    pooled = (sum(m["reply_words"] for m in months.values()) / total_replies) if total_replies else 0.0
    for m in months.values():
        per = m["reply_words"] / m["replies"] if m["replies"] >= 500 else pooled
        m["estimated_reply_words"] = round(m["prompts_without_reply"] * per)

    low, central, high = read_share
    totals = collections.Counter()
    for m in months.values():
        totals.update(m)
    basis_measured = totals["reply_words"]
    basis_estimated = totals["estimated_reply_words"]

    days = collections.Counter(_dt.datetime.fromtimestamp(r["ts"], zone).date() for r in written)
    hours = collections.Counter(_dt.datetime.fromtimestamp(r["ts"], zone).hour for r in written
                                if r["src"] != "export")
    harnesses = collections.Counter(r["harness"].split(":")[0] for r in written)
    lengths = [r["words"] for r in written]

    def ratio(a: float, b: float) -> Optional[float]:
        return round(a / b, 2) if b else None

    read_central = round((basis_measured + basis_estimated) * central)
    return {
        "read_share": {"low": low, "central": central, "high": high},
        "written": {
            "prompts": len(written),
            "words": totals["words_written"],
            "authored_words": totals["authored_words"],
            "median_words": statistics.median(lengths) if lengths else None,
        },
        "read": {
            "reply_words_measured": basis_measured,
            "reply_words_estimated": basis_estimated,
            "pooled_words_per_reply": round(pooled),
            "words_low": round((basis_measured + basis_estimated) * low),
            "words_central": read_central,
            "words_high": round((basis_measured + basis_estimated) * high),
            # The floor with no estimate at all: measured replies at the low share.
            "words_measured_only_low": round(basis_measured * low),
        },
        "ratio_read_to_written": ratio(read_central, totals["words_written"]),
        "agents_own": {"replies": totals["agent_replies"], "words": totals["agent_reply_words"]},
        "activity": {
            "active_days": len(days),
            "first_day": min(days).isoformat() if days else None,
            "last_day": max(days).isoformat() if days else None,
            "longest_streak": _streak(sorted(days)),
            "busiest_days": [{"day": d.isoformat(), "prompts": n} for d, n in days.most_common(5)],
            "by_hour": [hours.get(h, 0) for h in range(24)],
        },
        "by_harness": dict(harnesses.most_common()),
        "by_month": {k: dict(v) for k, v in sorted(months.items())},
        "dropped": dict(dropped),
    }


def _streak(days: List[_dt.date]) -> int:
    best = run = 0
    previous = None
    for day in days:
        run = run + 1 if previous is not None and (day - previous).days == 1 else 1
        best = max(best, run)
        previous = day
    return best
