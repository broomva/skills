"""Episodes: every session a person drove, rebuilt with its words. Code only, no model.

Who wrote a prompt, and which rows are one turn, are decided by
:func:`yia.ledger.attention.classify`, the same decisions ``attention`` counts.
This module never re-derives them. It reads the stores through the ledger's
own readers with a :class:`yia.ledger.text_tap`, so each row it sees has the
exact id the classification uses, and joins the text back by occurrence and
text hash. The ledger itself stays text-free.

An episode is one session (the opaque session hash every reader computes):
its human turns in the window, in order, each with the user's authored text
and the agent's trimmed final reply; where it ran (directory, repository,
branch); tickets and pull requests mentioned; skills and slash commands;
correction markers; and a size and correction score that picks which
sessions also get a sampled tool trace.
"""

from __future__ import annotations

import collections
import datetime as _dt
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from ..ledger import attention as A
from ..ledger import store as L
from ..ledger import text_tap
from . import episode_id, pr_urls_in, tickets_in
from . import traces as TR

#: Episodes per digest batch, and the most characters one batch may hold.
BATCH_SIZE = 25
BATCH_CHARS = 160_000
#: Sessions sampled for a tool trace, per criterion (longest, most corrected).
SAMPLE_PER_CRITERION = 30
#: Trace events kept in a sampled excerpt.
TRACE_EXCERPT = 90
#: A final reply is kept as its head and tail.
REPLY_HEAD, REPLY_TAIL = 500, 900

#: How a prompt redirects the agent. Anchored at the start, where a correction
#: is made; "no" mid-sentence is not one.
CORRECTION_START = re.compile(
    r"^\s*(?:no\b[,.!:\s]|nope\b|stop\b|wait\b|hold on\b|actually\b|not (?:that|this|what|quite)\b|"
    r"that'?s (?:not|wrong|incorrect)\b|that is (?:not|wrong)\b|this is (?:not|wrong)\b|wrong\b|"
    r"you (?:didn'?t|did not|missed|forgot|broke|ignored|skipped|misunderstood|are wrong)\b|"
    r"why (?:did|are|is|would|didn'?t) you\b|i (?:said|asked|told you|meant)\b|don'?t\b|do not\b|undo\b|"
    r"revert\b|instead\b|please (?:don'?t|stop|re-?read)\b|still (?:not|broken|failing|wrong|doesn'?t)\b|"
    r"it (?:still|doesn'?t|does not|didn'?t)\b|espera\b|pero no\b|eso no\b|no es\b|otra vez\b)",
    re.I,
)
#: Redirecting phrases anywhere in a prompt's first 300 characters.
CORRECTION_PHRASES = (
    "that's not what i", "that is not what i", "not what i asked", "i told you", "you didn't", "you did not",
    "you ignored", "you forgot", "try again", "same error", "still failing", "still broken", "didn't work",
    "doesn't work", "does not work", "wrong file", "wrong branch", "you missed", "re-read", "reread",
)

#: A slash command at the start of a prompt; a path such as ``/Users/x`` is not one.
_SLASH = re.compile(r"^\s*(/[a-z][\w:.-]*)(?=\s|$)", re.I)


def is_correction(text: str) -> Optional[str]:
    """The marker that makes this prompt a correction, or None."""
    if not text:
        return None
    match = CORRECTION_START.match(text)
    if match:
        return match.group(0).strip().lower()[:24]
    head = text[:300].lower().replace("’", "'")
    for phrase in CORRECTION_PHRASES:
        if phrase in head:
            return phrase
    return None


def trim_reply(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= REPLY_HEAD + REPLY_TAIL + 40:
        return text
    return text[:REPLY_HEAD].rstrip() + " […] " + text[-REPLY_TAIL:].lstrip()


# ------------------------------------------------------------------- collect


class TextSink:
    """Collects prompt and reply text by occurrence and text hash, inside a time window."""

    def __init__(self, lo: Optional[float], hi: Optional[float], margin: float = 3 * 86400):
        self.lo = None if lo is None else lo - margin
        self.hi = None if hi is None else hi + margin
        self.prompts: Dict[Tuple[str, str], str] = {}
        self.replies: Dict[Tuple[str, str], str] = {}

    def __call__(self, row: dict, text: str, authored: str) -> None:
        ts = row["ts"]
        if (self.lo is not None and ts < self.lo) or (self.hi is not None and ts >= self.hi):
            return
        key = (row["o"], row["h"])
        if row["kind"] == "prompt":
            self.prompts[key] = authored
        else:
            self.replies[key] = trim_reply(text)


def collect(roots: Dict[str, List[Path]], window: Tuple[float, float], ledger: Optional[L.Ledger],
            text_only_until: Optional[float], bridged_offset: float = -5.0, readers=None):
    """Read every store once with the text tap; classify ledger + fresh rows together.

    Returns ``(classification, sink, reports)``. Ledger rows give the fold its
    full context (prompts pruned from the stores still count toward the
    scripted-prompt filters); fresh rows add what the last harvest missed and
    carry the text.
    """
    lo, hi = window
    sink = TextSink(lo, hi)
    reports = []
    fresh: List[dict] = []
    since = lo - 3 * 86400 if lo is not None else None
    with text_tap(sink):
        for report, rows in (readers if readers is not None else L.readers(roots, since, bridged_offset)):
            fresh.extend(rows)
            reports.append(report.to_dict())
    stored: List[dict] = list(ledger.rows()) if ledger is not None else []
    ids = {r["id"] for r in stored}
    top = max([r["seq"] for r in stored if isinstance(r.get("seq"), int)] or [0])
    added = 0
    for r in fresh:
        if r["id"] in ids:
            continue
        added += 1
        stored.append(dict(r, seq=top + added))
        ids.add(r["id"])
    classification = A.classify(stored, text_only_until=text_only_until, window=window)
    return classification, sink, reports


# -------------------------------------------------------------------- build


def _local(ts: float, zone) -> str:
    return _dt.datetime.fromtimestamp(ts, zone).strftime("%Y-%m-%dT%H:%M")


def build(classification, sink: TextSink, metas: Dict[str, dict], utc_offset_hours: float = -5.0,
          ticket_prefixes: Optional[set] = None) -> List[dict]:
    """One episode per session with at least one human turn in the window that has text."""
    c = classification
    zone = _dt.timezone(_dt.timedelta(hours=utc_offset_hours))
    by_id = {r["id"]: r for r in c.prompts}
    members: Dict[str, List[str]] = collections.defaultdict(list)
    for pid, cid in c.human_canon.items():
        members[cid].append(pid)
    sessions: Dict[str, List[dict]] = collections.defaultdict(list)
    for r in c.human_kept:
        if not c.in_window(r["ts"]):
            continue
        key = r["sess"] or hashlib.sha1(f"{r['src']}|{_local(r['ts'], zone)[:10]}".encode()).hexdigest()[:16]
        sessions[key].append(r)

    episodes: List[dict] = []
    taken: set = set()
    for sess in sorted(sessions, key=lambda s: (min(r["ts"] for r in sessions[s]), s)):
        turns = []
        missing = 0
        for r in sorted(sessions[sess], key=lambda r: (r["ts"], r["id"])):
            ids = [r["id"]] + sorted(m for m in members[r["id"]] if m != r["id"])
            text = next((sink.prompts[(by_id[m]["o"], by_id[m]["h"])] for m in ids
                         if m in by_id and (by_id[m]["o"], by_id[m]["h"]) in sink.prompts), None)
            reply_row = c.human_replies.get(r["id"])
            reply = sink.replies.get((reply_row["o"], reply_row["h"])) if reply_row else None
            if text is None or not text.strip():
                missing += 1
                continue
            turns.append({"ts": r["ts"], "src": r["src"], "harness": r["harness"].split(":")[0],
                          "words": r.get("authored_words", r["words"]), "text": text,
                          "reply": reply, "reply_words": reply_row["words"] if reply_row else 0})
        if not turns:
            continue
        eid = episode_id(sess, taken)
        taken.add(eid)
        meta = metas.get(sess) or TR.new_meta()
        episodes.append(_episode(eid, sess, turns, missing, meta, zone))
    allowed = ticket_prefixes if ticket_prefixes is not None else tracker_prefixes(episodes)
    for e in episodes:
        e["tickets"] = sorted(t for t in e["tickets"] if t.split("-")[0] in allowed)
    _score(episodes)
    return episodes


#: Branch name parts that look like a ticket prefix but are not one.
NOT_A_PREFIX = {"FEAT", "FIX", "CHORE", "T3", "AGENT", "CLAUDE", "CODEX", "WT", "PR"}


def tracker_prefixes(episodes: List[dict]) -> set:
    """Ticket prefixes that are trackers here: in a branch name, or letters only on five or more distinct ids.

    ``E1-23`` style codes recur too, but tracker keys are letters; set config
    ``ticket_prefixes`` to override.
    """
    counts: Dict[str, set] = collections.defaultdict(set)
    for e in episodes:
        for t in e["tickets"]:
            counts[t.split("-")[0]].add(t)
    allowed = {p for p, ids in counts.items() if len(ids) >= 5 and p.isalpha()}
    for e in episodes:
        for prefix in re.findall(r"(?:^|/)([a-z][a-z0-9]{1,9})-[0-9]{1,6}(?=$|-|/)", e.get("branch") or "", re.I):
            if prefix.upper() not in NOT_A_PREFIX:
                allowed.add(prefix.upper())
    return allowed


def _episode(eid: str, sess: str, turns: List[dict], missing: int, meta: dict, zone) -> dict:
    prompts, replies, corrections = [], [], []
    for i, t in enumerate(turns):
        marker = is_correction(t["text"]) if i else None
        if marker:
            corrections.append({"i": i, "marker": marker})
        prompts.append({"i": i, "at": _local(t["ts"], zone), "text": t["text"], "words": t["words"],
                        "correction": bool(marker)})
        if t["reply"]:
            replies.append({"i": i, "text": t["reply"], "words": t["reply_words"]})
    corpus = "\n".join([p["text"] for p in prompts] + [r["text"] for r in replies]
                       + [meta.get("branch") or "", meta.get("title") or ""]
                       + [(info or {}).get("title") or "" for info in meta["prs"].values()])
    prs = sorted(pr_urls_in(corpus) | {u for u in meta["prs"] if "/pull/" in u})
    commands = collections.Counter(meta["commands"])
    for p in prompts:
        match = _SLASH.match(p["text"])
        if match and match.group(1).lower() not in TR.TRIVIAL_COMMANDS:
            commands[match.group(1).lower()] += 1
    harnesses = collections.Counter(t["harness"] for t in turns)
    interrupts = [ts for ts in meta["interrupts"] if ts is not None]
    days = sorted({p["at"][:10] for p in prompts})
    episode = {
        "id": eid,
        "session": sess,
        "first": prompts[0]["at"],
        "last": prompts[-1]["at"],
        "month": prompts[0]["at"][:7],
        "days": days,
        "harness": harnesses.most_common(1)[0][0],
        "stores": sorted({t["src"] for t in turns}),
        "repo": meta.get("repo"),
        "cwd": meta.get("cwd"),
        "branch": meta.get("branch"),
        "title": meta.get("title"),
        "project": meta.get("project"),
        "tickets": sorted(tickets_in(corpus)),
        "prs": prs,
        "harness_prs": {u: info for u, info in meta["prs"].items()},
        "skills": dict(meta["skills"].most_common()),
        "commands": dict(commands.most_common()),
        "tools": meta["tools"],
        "tool_errors": meta["tool_errors"],
        "subagents": meta["subagents"],
        "interrupts": len(interrupts),
        "corrections": corrections,
        "prompts": prompts,
        "prompts_without_text": missing,
        "replies": replies,
        "words": sum(p["words"] for p in prompts),
        "reply_words": sum(t["reply_words"] for t in turns),
        "events": meta["events"],
    }
    episode["hash"] = content_hash(episode)
    return episode


def content_hash(episode: dict) -> str:
    """What a digest is cached against: the prompts and replies, nothing derived."""
    body = json.dumps([[p["text"] for p in episode["prompts"]], [r["text"] for r in episode["replies"]]],
                      ensure_ascii=False)
    return hashlib.sha1(body.encode("utf-8")).hexdigest()[:16]


def _score(episodes: List[dict]) -> None:
    """Size and correction scores, and which sessions get a sampled tool trace."""
    for e in episodes:
        e["score"] = {
            "size": round(len(e["prompts"]) + e["tools"] / 25 + e["reply_words"] / 400
                          + math.log1p(e["words"]), 2),
            "corrections": len(e["corrections"]) + e["interrupts"],
        }
        e["sampled"] = []
    longest = sorted(episodes, key=lambda e: (-e["score"]["size"], e["id"]))[:SAMPLE_PER_CRITERION]
    corrected = sorted([e for e in episodes if e["score"]["corrections"]],
                       key=lambda e: (-e["score"]["corrections"], -e["score"]["size"], e["id"]))[:SAMPLE_PER_CRITERION]
    for label, group in (("longest", longest), ("most-corrected", corrected)):
        for e in group:
            e["sampled"].append(label)
    for e in episodes:
        e["trace"] = excerpt(e) if e["sampled"] and e["events"] else None


def excerpt(episode: dict, limit: int = TRACE_EXCERPT) -> List[str]:
    """The trace around what matters: the opening, each correction and error, and the close."""
    events = episode["events"]
    if len(events) <= limit:
        chosen = list(range(len(events)))
    else:
        keep = set(range(15)) | set(range(len(events) - 15, len(events)))
        marks = [p for p in episode["prompts"] if p["correction"]]
        times = [e[0] for e in events]
        for p in marks:
            at = _dt.datetime.strptime(p["at"], "%Y-%m-%dT%H:%M").timestamp()
            nearest = min(range(len(events)), key=lambda i: abs((times[i] or 0) - at))
            keep |= set(range(max(0, nearest - 3), min(len(events), nearest + 4)))
        keep |= {i for i, ev in enumerate(events) if ev[2]}
        chosen = sorted(keep)[:limit]
    out, previous = [], -1
    for i in chosen:
        if previous >= 0 and i != previous + 1:
            out.append(f"… {i - previous - 1} events …")
        ev = events[i]
        out.append(("✗ " if ev[2] else "  ") + ev[1])
        previous = i
    return out


# ------------------------------------------------------------------- batches


def batch_view(e: dict, max_prompts: int = 80, max_chars: int = 2400) -> dict:
    """What a digest subagent sees of one episode."""
    prompts = e["prompts"]
    omitted = 0
    if len(prompts) > max_prompts:
        keep = set(range(30)) | set(range(len(prompts) - 30, len(prompts))) | {p["i"] for p in prompts if p["correction"]}
        omitted = len(prompts) - len(keep)
        prompts = [p for p in prompts if p["i"] in keep]
    shown = {p["i"] for p in prompts}
    replies = [r for r in e["replies"] if r["i"] in shown]
    if sum(len(r["text"]) for r in replies) > 14_000:
        last = {r["i"] for r in replies[-4:]} | {p["i"] for p in prompts if p["correction"]}
        replies = [r if r["i"] in last else {"i": r["i"], "text": r["text"][:300]} for r in replies]
    view = {
        "id": e["id"], "hash": e["hash"], "first": e["first"], "last": e["last"], "harness": e["harness"],
        "repo": e["repo"], "branch": e["branch"], "title": e["title"], "tickets": e["tickets"], "prs": e["prs"],
        "merged_prs_seen_by_harness": [u for u, i in e["harness_prs"].items() if (i or {}).get("state") == "merged"],
        "skills": e["skills"], "commands": e["commands"], "tools": e["tools"], "tool_errors": e["tool_errors"],
        "interrupts": e["interrupts"], "corrections": e["corrections"],
        "prompts": [{"i": p["i"], "at": p["at"], "correction": p["correction"],
                     "text": p["text"] if len(p["text"]) <= max_chars else p["text"][:max_chars] + " […]"}
                    for p in prompts],
        "prompts_omitted": omitted,
        "replies": [{"i": r["i"], "text": r["text"]} for r in replies],
    }
    if e.get("trace"):
        view["trace_sample"] = {"why": e["sampled"], "events": e["trace"]}
    return view


def batches(episodes: List[dict], pending: Iterable[str]) -> List[List[dict]]:
    """Batches of about :data:`BATCH_SIZE` episodes needing a digest, in time order."""
    wanted = set(pending)
    out: List[List[dict]] = []
    current: List[dict] = []
    size = 0
    for e in episodes:
        if e["id"] not in wanted:
            continue
        view = batch_view(e)
        n = len(json.dumps(view, ensure_ascii=False))
        if current and (len(current) >= BATCH_SIZE or size + n > BATCH_CHARS):
            out.append(current)
            current, size = [], 0
        current.append(view)
        size += n
    if current:
        out.append(current)
    return out


