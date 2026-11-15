"""Words you wrote and words you read, folded from the ledger.

The unit is the **turn**: one prompt and the final reply to it. A store can
record a turn more than once (a resumed session copies its history), and two
stores can record the same turn. The fold resolves those to one canonical turn
from evidence, never from text alone:

* **Copies inside one store** need the store's own message id (``k``): a
  resumed Claude Code session copies records with their original ``uuid``.
  Stores without ids (bridged markdown, exports) need session lineage: the
  same text at the same moment in two sessions, *and* a neighbouring turn that
  also matches. A lone ``yes`` typed in two sessions stays two turns.
* **One turn in several stores** merges with the closest same-text turn of
  another store inside a window (36 hours; 20 minutes under 80 characters),
  each canonical turn claimed at most once per store. Two prompts in one store
  are never merged by this pass.

**Written** counts canonical turns whose prompt a person wrote:

1. its store says a person wrote it (``author == "human"``), or its store
   records no author (``unknown``) and it comes from a text-only source that
   has passed the filters below;
2. it is not scripted: no automation marker, its exact text does not recur in
   three or more sessions (150+ characters), and its opening does not recur in
   four or more sessions (40+ characters). Skipped for stores with an exact
   author flag (T3): a person may paste one brief into several threads.

**Read** counts the final reply to each counted turn, times a stated read share
(default band 60-70%). Within a store the latest revision of a turn's reply
wins; across stores the turn's own store wins, then store priority. A turn
recorded only by stores that never keep replies gets an estimated reply (the
month's measured mean with 500+ replies, else the pooled mean), reported
separately. Replies to agent-written prompts are the agents' own volume.

``window`` limits what is *reported*; rows outside it are still used as
context, so a reply just inside the window keeps the prompt just before it.
A turn's reply is its final revision, wherever that falls: it is what was
read, and it is read when it was written. A turn whose final revision lands
after the window is reported in the period that contains it, not this one.

Memory: the fold holds the selected rows in memory. Rows are per turn, not per
transcript byte; one measured year of heavy multi-harness use was ~80k rows
(25 MB on disk), so this is deliberate.
"""

from __future__ import annotations

import bisect
import collections
import datetime as _dt
import statistics
from typing import Dict, Iterable, List, Optional, Tuple

#: Store priority: the canonical turn comes from the first store in this list.
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
#: Timestamp precision of text-only stores, in seconds: bridged markdown records
#: minutes; exports place turns at synthetic one-second steps.
COPY_PRECISION = {"bridged": 60.0, "export": 1.0}
#: Reasons a prompt is neither the person's writing nor the agents' own.
EXCLUDED_REASONS = {"text-only after exact coverage", "unknown author"}


def _month(ts: float, zone: _dt.tzinfo) -> str:
    return _dt.datetime.fromtimestamp(ts, zone).strftime("%Y-%m")


def _rank(src: str) -> int:
    return PRIORITY.index(src) if src in PRIORITY else len(PRIORITY)


def _order(r: dict) -> Tuple:
    """A total order on rows, so every choice below is independent of input order."""
    return (_rank(r["src"]), r["ts"], r["id"])


def fold(rows: Iterable[dict], read_share=(0.60, 0.65, 0.70), utc_offset_hours: float = -5.0,
         text_only_until: Optional[float] = None,
         window: Optional[Tuple[Optional[float], Optional[float]]] = None) -> dict:
    """Fold ledger rows into the written/read summary.

    ``text_only_until``: ignore text-only sources from this time on. Use it once
    a store with exact authors covers the period: measured on 2026-10-18 to
    2026-11-13, only ~18% of bridged prompts matched a human-typed T3 prompt.
    """
    zone = _dt.timezone(_dt.timedelta(hours=utc_offset_hours))
    lo, hi = window or (None, None)

    def in_window(ts: float) -> bool:
        return (lo is None or ts >= lo) and (hi is None or ts < hi)

    # One id is one revision of one occurrence (see the reader contract). Keep
    # each occurrence's latest revision: the last one appended to the ledger.
    # Replies that point at an older revision of their prompt follow the alias.
    latest: Dict[str, dict] = {}
    revisions: Dict[str, List[str]] = collections.defaultdict(list)
    for r in rows:
        occ = r.get("o") or r["id"]
        if r["id"] not in revisions[occ]:
            revisions[occ].append(r["id"])
        latest[occ] = r
    alias: Dict[str, str] = {}
    for occ, ids in revisions.items():
        for rid in ids:
            alias[rid] = latest[occ]["id"]
    rows = [dict(r, turn=alias.get(r.get("turn"), r.get("turn"))) if r["kind"] == "reply" else r
            for r in latest.values()]
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

    def why_not_written(r: dict) -> Optional[str]:
        src = r["src"]
        if text_only_until is not None and src in TEXT_ONLY and r["ts"] >= text_only_until:
            return "text-only after exact coverage"
        if r["author"] == "agent":
            return "agent author"
        if r["author"] == "unknown" and src not in TEXT_ONLY:
            return "unknown author"
        if src not in EXACT_AUTHOR:
            if "marker" in r.get("flags", ()):
                return "automation marker"
            if r["h"] in repeated_text:
                return "repeated text"
            if r.get("ph") in repeated_open:
                return "repeated opening"
            if src in TEXT_ONLY and r["chars"] > UNFLAGGED_MAX_CHARS:
                return "long unflagged"
        return None

    human_ids = set()
    agent_ids = set()
    for r in prompts:
        reason = why_not_written(r)
        if reason is None:
            human_ids.add(r["id"])
        else:
            # The agents' own volume is what agents wrote: an agent author, or a
            # prompt filtered as scripted. A row cut by `text_only_until`, or one
            # whose store records no author (an SDK app such as T3 driving Claude,
            # already counted from T3 itself), is excluded from both sides.
            if reason not in EXCLUDED_REASONS:
                agent_ids.add(r["id"])
            if in_window(r["ts"]):
                dropped[reason] += 1

    sequences = session_sequences(prompts)
    human_kept, human_canon = canonical_turns([r for r in prompts if r["id"] in human_ids], sequences,
                                              dropped, "prompt", in_window)
    _agent_kept, agent_canon = canonical_turns([r for r in prompts if r["id"] in agent_ids], sequences,
                                               dropped, "agent prompt", in_window)
    prompt_src = {r["id"]: r["src"] for r in prompts}
    replies = [r for r in rows if r["kind"] == "reply"]
    human_replies = pick_replies(replies, human_canon, prompt_src, dropped)
    agent_replies = pick_replies(replies, agent_canon, prompt_src, dropped)

    # Which stores recorded each canonical turn: a turn needs an estimated reply
    # only when no reply was resolved for it and only reply-less stores saw it.
    members: Dict[str, set] = collections.defaultdict(set)
    for pid, cid in human_canon.items():
        members[cid].add(prompt_src[pid])

    written = [r for r in human_kept if in_window(r["ts"])]
    months: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for r in written:
        m = months[_month(r["ts"], zone)]
        m["prompts"] += 1
        m["words_written"] += r["words"]
        m["authored_words"] += r.get("authored_words", r["words"])
        if r["id"] not in human_replies and members[r["id"]] <= NO_REPLIES:
            m["prompts_without_reply"] += 1
    for r in human_replies.values():
        if in_window(r["ts"]):
            m = months[_month(r["ts"], zone)]
            m["replies"] += 1
            m["reply_words"] += r["words"]
    for r in agent_replies.values():
        if in_window(r["ts"]):
            m = months[_month(r["ts"], zone)]
            m["agent_replies"] += 1
            m["agent_reply_words"] += r["words"]

    total_replies = sum(m["replies"] for m in months.values())
    pooled = (sum(m["reply_words"] for m in months.values()) / total_replies) if total_replies else 0.0
    for m in months.values():
        per = m["reply_words"] / m["replies"] if m["replies"] >= 500 else pooled
        m["estimated_reply_words"] = round(m["prompts_without_reply"] * per)

    low, central, high = read_share
    totals: collections.Counter = collections.Counter()
    for m in months.values():
        totals.update(m)
    basis_measured = totals["reply_words"]
    basis_estimated = totals["estimated_reply_words"]
    basis = basis_measured + basis_estimated

    days = collections.Counter(_dt.datetime.fromtimestamp(r["ts"], zone).date() for r in written)
    hours = collections.Counter(_dt.datetime.fromtimestamp(r["ts"], zone).hour for r in written
                                if r["src"] != "export")
    harnesses = collections.Counter(r["harness"].split(":")[0] for r in written)
    lengths = [r["words"] for r in written]
    read_central = round(basis * central)
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
            "words_low": round(basis * low),
            "words_central": read_central,
            "words_high": round(basis * high),
            # The floor with no estimate at all: measured replies at the low share.
            "words_measured_only_low": round(basis_measured * low),
        },
        "ratio_read_to_written": round(read_central / totals["words_written"], 2) if totals["words_written"] else None,
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


class Sequences:
    """Every session's prompts in order, per store, with each row's position. The evidence for lineage."""

    def __init__(self, prompts: List[dict]):
        self.by_session: Dict[Tuple[str, str], List[dict]] = collections.defaultdict(list)
        for r in sorted(prompts, key=lambda r: (r["ts"], r["id"])):
            self.by_session[(r["src"], r["sess"])].append(r)
        self.position: Dict[str, int] = {}
        for seq in self.by_session.values():
            for i, r in enumerate(seq):
                self.position[r["id"]] = i

    def neighbour(self, r: dict, step: int) -> Optional[dict]:
        seq = self.by_session[(r["src"], r["sess"])]
        j = self.position[r["id"]] + step
        return seq[j] if 0 <= j < len(seq) else None


def session_sequences(prompts: List[dict]) -> "Sequences":
    return Sequences(prompts)


def _same_moment(a: dict, b: dict, precision: float) -> bool:
    return a["h"] == b["h"] and abs(a["ts"] - b["ts"]) <= precision


def _neighbours_match(a: dict, b: dict, seqs: "Sequences", precision: float) -> bool:
    """Do the turns before or after ``a`` and ``b`` in their sessions also match?"""
    for step in (-1, 1):
        na, nb = seqs.neighbour(a, step), seqs.neighbour(b, step)
        if na is not None and nb is not None and _same_moment(na, nb, precision):
            return True
    return False


class _TimeIndex:
    """Rows of one text hash, per store, sorted by time, for nearest-neighbour lookups."""

    def __init__(self) -> None:
        self.times: Dict[str, List[float]] = collections.defaultdict(list)
        self.rows: Dict[str, List[dict]] = collections.defaultdict(list)

    def add(self, r: dict) -> None:
        i = bisect.bisect_right(self.times[r["src"]], r["ts"])
        self.times[r["src"]].insert(i, r["ts"])
        self.rows[r["src"]].insert(i, r)

    def near(self, src: str, ts: float, radius: float):
        """Rows of ``src`` within ``radius`` of ``ts``, nearest first (ties by id), lazily.

        Walks outward from the insertion point, so a caller that stops at the
        first acceptable candidate touches only the rows it passes over.
        """
        times, rows = self.times.get(src, []), self.rows.get(src, [])
        right = bisect.bisect_left(times, ts)
        left = right - 1
        while True:
            lgap = ts - times[left] if left >= 0 else None
            rgap = times[right] - ts if right < len(times) else None
            if lgap is not None and lgap > radius:
                lgap, left = None, -1
            if rgap is not None and rgap > radius:
                rgap, right = None, len(times)
            if lgap is None and rgap is None:
                return
            # Equal gaps: take the smaller id first, so the order never depends on insertion order.
            take_left = rgap is None or (lgap is not None and (lgap, rows[left]["id"]) <= (rgap, rows[right]["id"]))
            if take_left:
                yield rows[left]
                left -= 1
            else:
                yield rows[right]
                right += 1


#: The widest cross-store window; per-pair windows are narrower (see :func:`_window`).
MAX_MATCH_WINDOW = 36 * 3600


def _window(a: dict, b: dict) -> float:
    if "export" in (a["src"], b["src"]):
        return 36 * 3600  # exports carry a date per session, not a time per turn
    return 36 * 3600 if max(a["chars"], b["chars"]) >= 80 else 20 * 60


def canonical_turns(items: List[dict], seqs, dropped: Dict[str, int], label: str, in_window=lambda ts: True):
    """Resolve rows to canonical turns. Returns the kept rows and a map from every row id to its turn id."""
    canon: Dict[str, str] = {}

    # Pass 1: copies inside one store, on evidence only.
    originals: List[dict] = []
    by_key: Dict[Tuple[str, str], dict] = {}
    by_moment: Dict[str, _TimeIndex] = collections.defaultdict(_TimeIndex)
    for r in sorted(items, key=lambda r: (r["src"], r["ts"], r["id"])):
        original = None
        if r.get("k"):
            original = by_key.get((r["src"], r["k"]))
        elif r["src"] in COPY_PRECISION:
            precision = COPY_PRECISION[r["src"]]
            for c in by_moment[r["h"]].near(r["src"], r["ts"], precision):
                if c["sess"] != r["sess"] and _neighbours_match(c, r, seqs, precision):
                    original = c
                    break
        if original is not None:
            canon[r["id"]] = original["id"]
            if in_window(r["ts"]):
                dropped[f"copied {label}"] += 1
            continue
        if r.get("k"):
            by_key[(r["src"], r["k"])] = r
        by_moment[r["h"]].add(r)
        originals.append(r)

    # Pass 2: one turn recorded by several stores; the closest candidate wins.
    by_hash: Dict[str, _TimeIndex] = collections.defaultdict(_TimeIndex)
    claimed: Dict[str, set] = collections.defaultdict(set)
    kept: List[dict] = []
    for r in sorted(originals, key=_order):
        best = None
        index = by_hash.get(r["h"])
        for src in sorted(index.rows) if index else ():
            if src == r["src"]:
                continue
            for c in index.near(src, r["ts"], MAX_MATCH_WINDOW):
                if r["src"] in claimed[c["id"]]:
                    continue
                gap = abs(c["ts"] - r["ts"])
                if gap <= _window(c, r) and (best is None or (gap, c["id"]) < best[0]):
                    best = ((gap, c["id"]), c)
                break  # nearest unclaimed candidate of this store
        if best is not None:
            match = best[1]
            claimed[match["id"]].add(r["src"])
            canon[r["id"]] = match["id"]
            if in_window(r["ts"]):
                dropped[f"duplicate {label}"] += 1
            continue
        canon[r["id"]] = r["id"]
        claimed[r["id"]].add(r["src"])
        by_hash[r["h"]].add(r)
        kept.append(r)

    # Copies point at an original that may itself have merged into another store's turn.
    for rid in list(canon):
        target = canon[rid]
        seen = {rid}
        while canon.get(target, target) != target and target not in seen:
            seen.add(target)
            target = canon[target]
        canon[rid] = target
    return kept, canon


def pick_replies(replies: List[dict], canon: Dict[str, str], prompt_src: Dict[str, str],
                 dropped: Dict[str, int]) -> Dict[str, dict]:
    """At most one final reply per canonical turn, chosen independently of input order.

    Within a store, the latest revision wins (then more words, then id). Across
    stores, the canonical prompt's own store wins, then store priority, then id.
    Returns ``{canonical turn id: reply row}``.
    """
    per_store: Dict[Tuple[str, str], dict] = {}
    for r in replies:
        turn = r.get("turn")
        if turn not in canon:
            continue
        key = (canon[turn], r["src"])
        current = per_store.get(key)
        if current is None or (r["ts"], r["words"], r["id"]) > (current["ts"], current["words"], current["id"]):
            if current is not None:
                dropped["superseded reply revision"] += 1
            per_store[key] = r
        else:
            dropped["superseded reply revision"] += 1
    chosen: Dict[str, Tuple[Tuple, dict]] = {}
    for (cid, src), r in per_store.items():
        preference = (0 if prompt_src.get(cid) == src else 1, _rank(src), r["id"])
        if cid in chosen:
            dropped["duplicate reply"] += 1
            if preference >= chosen[cid][0]:
                continue
        chosen[cid] = (preference, r)
    return {cid: r for cid, (_p, r) in chosen.items()}


def _streak(days: List[_dt.date]) -> int:
    best = run = 0
    previous = None
    for day in days:
        run = run + 1 if previous is not None and (day - previous).days == 1 else 1
        best = max(best, run)
        previous = day
    return best
