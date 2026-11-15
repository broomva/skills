"""Words you wrote and words you read, folded from the ledger.

**Written** counts prompts a person wrote. A prompt counts when:

1. its store says a person wrote it (``author == "human"``), or its store
   records no author (``unknown``) and it comes from a text-only source
   (bridged markdown, exports) that has passed the filters below;
2. it is not scripted: no automation marker, its exact text does not recur in
   three or more sessions (150+ characters), and its opening does not recur in
   four or more sessions (40+ characters);
3. it is not the same turn already counted from another store: same text,
   within 36 hours (20 minutes for prompts under 80 characters). Two
   identical prompts in one store are two turns.

Filter 2 is skipped for stores with an exact author flag (T3): a person may
paste the same brief into several threads, and the store has already said who
wrote it.

**Read** counts the final reply to each counted prompt, times a read share.
The share is an assumption the reader states, not a measurement; the default
band is 60-70%. Prompts from stores that never kept replies (prompt histories)
get an estimated reply: the month's measured mean if it has 500 or more
replies, else the pooled mean. Estimated words are reported separately.

Replies to agent-written prompts are reported as the agents' own volume and
excluded from what was read. Each turn contributes at most one reply: the
latest revision in its own store (see :func:`pick_replies`).

Memory: the fold holds the selected rows in memory. Rows are per turn, not
per transcript byte; one measured year of heavy multi-harness use was ~80k
rows (25 MB on disk), so this is deliberate.
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
#: Timestamp precision per store, in seconds. The same text in another session of
#: the same store within this distance is a copied turn (a resumed or forked
#: session), not a new one. Bridged markdown records minutes; others record
#: milliseconds; exports place turns at synthetic one-second steps.
COPY_PRECISION = {"bridged": 60.0}


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

    written, human_canon = canonical_turns([r for r in prompts if r["id"] in human_ids], dropped, "prompt")
    _agent_kept, agent_canon = canonical_turns([r for r in prompts if r["id"] not in human_ids], dropped,
                                               "agent prompt")
    prompt_src = {r["id"]: r["src"] for r in prompts}
    human_replies = pick_replies([r for r in rows if r["kind"] == "reply"], human_canon, prompt_src, dropped)
    agent_replies = pick_replies([r for r in rows if r["kind"] == "reply"], agent_canon, prompt_src, dropped)

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


def _window(a: dict, b_src: str, b_chars: int) -> float:
    if "export" in (a["src"], b_src):
        return 36 * 3600  # exports carry a date per session, not a time per turn
    return 36 * 3600 if max(a["chars"], b_chars) >= 80 else 20 * 60


def canonical_turns(items: List[dict], dropped: Dict[str, int], label: str):
    """Merge one turn recorded by several stores into a single canonical prompt.

    Rows from the same store are always distinct turns: two identical prompts
    typed in one store were typed twice. A row from another store merges into
    an existing turn with the same text inside the time window, and each
    canonical turn can be claimed at most once per store, so two "yes" turns
    in one store and two in another stay two turns, not one.

    Returns the kept prompts and a map from every prompt id to its canonical id.
    """
    items = sorted(items, key=lambda r: (_rank(r["src"]), r["ts"]))
    canon: Dict[str, str] = {}

    # Pass 1: copies inside one store. A resumed or forked session carries its
    # history into a new session with the original timestamps, so the same text
    # in a different session at the same moment is one turn recorded twice.
    originals: List[dict] = []
    last_seen: Dict[tuple, dict] = {}
    for r in sorted(items, key=lambda r: (r["src"], r["h"], r["ts"])):
        key = (r["src"], r["h"])
        prior = last_seen.get(key)
        precision = COPY_PRECISION.get(r["src"], 1.0)
        if prior is not None and prior["sess"] != r["sess"] and abs(r["ts"] - prior["ts"]) <= precision:
            canon[r["id"]] = prior["id"]
            dropped[f"copied {label}"] += 1
            continue
        last_seen[key] = r
        originals.append(r)
    items = sorted(originals, key=lambda r: (_rank(r["src"]), r["ts"]))

    # Pass 2: one turn recorded by several stores.
    by_hash: Dict[str, List[dict]] = collections.defaultdict(list)
    claimed: Dict[str, set] = collections.defaultdict(set)  # canonical id -> stores merged into it
    kept: List[dict] = []
    for r in items:
        match = None
        for c in by_hash[r["h"]]:
            if c["src"] == r["src"] or r["src"] in claimed[c["id"]]:
                continue
            if abs(c["ts"] - r["ts"]) <= _window(c, r["src"], r["chars"]):
                match = c
                break
        if match is not None:
            claimed[match["id"]].add(r["src"])
            canon[r["id"]] = match["id"]
            dropped[f"duplicate {label}"] += 1
            continue
        canon[r["id"]] = r["id"]
        claimed[r["id"]].add(r["src"])
        by_hash[r["h"]].append(r)
        kept.append(r)
    # Copies point at an original that may itself have merged into another store's turn.
    for rid, target in list(canon.items()):
        while canon.get(target, target) != target:
            target = canon[target]
        canon[rid] = target
    return kept, canon


def pick_replies(replies: List[dict], canon: Dict[str, str], prompt_src: Dict[str, str],
                 dropped: Dict[str, int]) -> List[dict]:
    """At most one final reply per canonical turn.

    A harvest that runs mid-turn records the reply as it stood; a later
    harvest records the final one. Within a store, the latest revision of a
    turn's reply wins. Across stores, the canonical prompt's own store wins,
    then store priority.
    """
    latest: Dict[tuple, dict] = {}
    for r in replies:
        turn = r.get("turn")
        if turn not in canon:
            continue
        key = (r["src"], turn)
        if key in latest:
            dropped["superseded reply revision"] += 1
            if (r["ts"], r["words"]) <= (latest[key]["ts"], latest[key]["words"]):
                continue
        latest[key] = r
    chosen: Dict[str, dict] = {}
    for (src, turn), r in latest.items():
        cid = canon[turn]
        own = prompt_src.get(cid) == src
        rank = (0 if own else 1, _rank(src))
        if cid in chosen:
            dropped["duplicate reply"] += 1
            if rank >= chosen[cid][0]:
                continue
        chosen[cid] = (rank, r)
    return [r for _rank_key, r in chosen.values()]


def _streak(days: List[_dt.date]) -> int:
    best = run = 0
    previous = None
    for day in days:
        run = run + 1 if previous is not None and (day - previous).days == 1 else 1
        best = max(best, run)
        previous = day
    return best
