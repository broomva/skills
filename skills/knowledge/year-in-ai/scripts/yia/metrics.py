"""Fold a stream of :class:`~yia.model.Event` into the payload.

Everything here is a single pass.  Readers are generators over tens of
gigabytes, so the aggregator may keep only per-session and per-bucket state —
never the events themselves.

Two measurement choices are worth stating plainly, because both could be done
more flatteringly and less honestly:

*Active time* is the sum of gaps between consecutive events in a session,
with any gap longer than :data:`IDLE_GAP_SECONDS` discarded.  Last-minus-first
would count a session left open overnight as eight hours of work.

*Phrase counts* are drawn from a bounded word budget.  When the budget is
exhausted the payload says so, so a phrase count is never presented as
exhaustive when it was truncated.
"""

from __future__ import annotations

import datetime as _dt
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import median
from typing import Any

from .model import Event, Provenance, Window
from .personality import BUILD_TOOLS, DELEGATE_TOOLS, EXPLORE_TOOLS, is_correction

#: A gap longer than this means the operator walked away, not that they worked.
IDLE_GAP_SECONDS = 30 * 60

#: Only these sources may *create* a session. The prompt-history store records
#: one id per typed prompt, including automated probes, so letting it mint
#: sessions inflates the count and collapses the median session length.
SESSION_AUTHORITATIVE = frozenset({"claude_code", "codex"})

#: Text that the harness injected into the turn rather than the operator typing.
#: These land in the transcript as ordinary user messages, and counting them
#: turns the "things you kept saying" card into a list of file paths.
MACHINE_MARKERS = (
    "<task-notification>", "<system-reminder>", "<local-command-stdout>",
    "<command-name>", "<command-message>", "[system notification",
    "caveat: the messages below", "tool-use-id", "output-file",
    "this is an automated background-task event", "<user-prompt-submit-hook>",
    "session cwd remains", "command running in background with id",
)

#: A session needs at least this many events before its length is used in the
#: median or the Marathon/Sprint axis. Probe and scratchpad sessions are real
#: sessions, but a corpus full of two-event runs drags the median to under a
#: minute and says nothing about how the operator actually works.
MIN_SESSION_EVENTS = 5

#: Hours counted as "the night shift".
NIGHT_HOURS = range(0, 6)

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

_WORD = re.compile(r"[a-z][a-z'-]+")

#: Pasted material inside an otherwise genuine prompt. A person really did type
#: "please fix this"; they did not type the stack trace they pasted under it, and
#: counting the trace turns the phrase card into a list of file paths.
_NOISE = (
    re.compile(r"```.*?```", re.S),                     # fenced code
    re.compile(r"~~~.*?~~~", re.S),
    re.compile(r"<[^>\n]{1,200}>"),                     # xml/html-ish tags
    re.compile(r"\bhttps?://\S+"),                      # urls
    re.compile(r"[A-Za-z]:\\[\\\w.-]+"),                 # windows paths
    re.compile(r"~?(?:/[\w.@+-]+){2,}/?"),               # posix paths
    re.compile(r"^\s*[⎿│├└─›»$>|+-]{1,4}\s.*$", re.M),  # terminal gutters
    re.compile(r"\b[0-9a-f]{8,}\b", re.I),              # hashes and ids
)


def clean_prompt_text(text: str) -> str:
    """Strip pasted material so phrase counts reflect what was actually written."""
    for pattern in _NOISE:
        text = pattern.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "is", "it", "for", "on", "with",
    "that", "this", "be", "are", "as", "at", "by", "from", "we", "you", "i", "if",
    "so", "do", "can", "will", "has", "have", "was", "were", "not", "but", "into",
}


class PhraseCounter:
    """Bounded n-gram counter over prompt text.

    The budget exists because a full corpus of prompts would otherwise dominate
    memory.  ``exhausted`` is reported alongside the counts so the card can say
    "of the first N words" rather than implying it read everything.
    """

    def __init__(self, n: int = 3, word_budget: int = 2_000_000) -> None:
        self.n = n
        self.word_budget = word_budget
        self.words_seen = 0
        self.prompts_seen = 0
        self.counts: Counter[tuple[str, ...]] = Counter()

    @property
    def exhausted(self) -> bool:
        return self.words_seen >= self.word_budget

    def add(self, text: str | None) -> None:
        if not text or self.exhausted:
            return
        self.prompts_seen += 1
        words = _WORD.findall(text.lower())
        remaining = self.word_budget - self.words_seen
        if len(words) > remaining:
            words = words[:remaining]
        self.words_seen += len(words)
        for i in range(len(words) - self.n + 1):
            gram = tuple(words[i : i + self.n])
            # A phrase made only of stopwords carries no signal.
            if all(w in _STOP for w in gram):
                continue
            self.counts[gram] += 1

    def top(self, limit: int = 10, min_count: int = 3) -> list[dict[str, Any]]:
        return [
            {"phrase": " ".join(gram), "count": count}
            for gram, count in self.counts.most_common(limit * 4)
            if count >= min_count
        ][:limit]


@dataclass(slots=True)
class SessionAcc:
    """Per-session accumulator; there are thousands of these, not millions."""

    first: _dt.datetime
    last: _dt.datetime
    active_seconds: float = 0.0
    messages: int = 0
    tool_calls: int = 0
    project: str | None = None
    branch: str | None = None
    source: str | None = None

    def advance(self, ts: _dt.datetime) -> None:
        gap = (ts - self.last).total_seconds()
        if 0 < gap <= IDLE_GAP_SECONDS:
            self.active_seconds += gap
        if ts > self.last:
            self.last = ts
        if ts < self.first:
            self.first = ts


#: A turn that opens with an XML-ish tag was assembled by a harness. Both
#: vendors inject context this way and both label it ``role="user"`` — Codex
#: alone files ``<recommended_plugins>`` under that role. Matching the shape
#: generalises where a list of known tag names would need endless extension.
_LEADING_TAG = re.compile(r"^\s*<[a-z_][\w:.-]*(?:\s[^>]*)?>", re.I)


def looks_machine_generated(text: str) -> bool:
    """Was this turn injected by the harness rather than typed by a person?"""
    if _LEADING_TAG.match(text):
        return True
    lowered = text.lower()
    return any(marker in lowered for marker in MACHINE_MARKERS)


def _rank(counter: Counter[str], limit: int = 10) -> list[dict[str, Any]]:
    total = sum(counter.values())
    return [
        {"name": name, "count": count, "share": round(count / total, 4) if total else 0.0}
        for name, count in counter.most_common(limit)
    ]


def longest_streak(days: set[_dt.date]) -> dict[str, Any] | None:
    """Longest run of consecutive active days."""
    if not days:
        return None
    ordered = sorted(days)
    best_len, best_end = 1, ordered[0]
    run_len = 1
    for prev, cur in zip(ordered, ordered[1:]):
        run_len = run_len + 1 if (cur - prev).days == 1 else 1
        if run_len > best_len:
            best_len, best_end = run_len, cur
    return {
        "days": best_len,
        "start": (best_end - _dt.timedelta(days=best_len - 1)).isoformat(),
        "end": best_end.isoformat(),
    }


class Aggregator:
    """Folds events into counters. One instance per run."""

    def __init__(self, window: Window) -> None:
        self.window = window
        self.provenance = Provenance()

        self.tools: Counter[str] = Counter()
        self.skills: Counter[str] = Counter()
        self.models: Counter[str] = Counter()
        self.projects: Counter[str] = Counter()
        self.branches: Counter[str] = Counter()
        self.mcp: Counter[str] = Counter()
        self.by_source: Counter[str] = Counter()

        self.by_hour = [0] * 24
        self.by_weekday = [0] * 7
        self.by_month: Counter[str] = Counter()
        self.active_days: set[_dt.date] = set()

        self.sessions: dict[str, SessionAcc] = {}
        self.tokens: dict[str, int] = defaultdict(int)

        self.user_messages = 0
        self.assistant_messages = 0
        self.tool_calls = 0
        self.corrections = 0
        self.prompts_scanned = 0
        self.machine_prompts_skipped = 0
        self.automated_prompts_skipped = 0
        self.interactive_prompts = 0

        self.phrases = PhraseCounter()
        self._prompt_digests: set[int] = set()
        self.template_prompts_skipped = 0
        self.first_prompt: dict[str, Any] | None = None
        self._events = 0

    # -- ingestion ---------------------------------------------------------

    def add(self, event: Event) -> None:
        ts = event.ts
        if not self.window.contains(ts):
            return
        self._events += 1
        self.window.observe(ts)
        self.by_source[event.source] += 1

        # Rhythm buckets exclude the legacy Codex format, whose items all share
        # one session timestamp and would spike a single hour artificially.
        self.by_hour[ts.hour] += 1
        self.by_weekday[ts.weekday()] += 1
        self.by_month[ts.strftime("%Y-%m")] += 1
        self.active_days.add(ts.date())

        if event.session:
            acc = self.sessions.get(event.session)
            if acc is None and event.source not in SESSION_AUTHORITATIVE:
                acc = None  # observe the event, but do not mint a session from it
            elif acc is None:
                self.sessions[event.session] = acc = SessionAcc(
                    first=ts, last=ts, project=event.project,
                    branch=event.branch, source=event.source,
                )
            else:
                acc.advance(ts)
            if acc is not None:
                acc.messages += 1
                if event.branch and not acc.branch:
                    acc.branch = event.branch
                if event.project and not acc.project:
                    acc.project = event.project

        if event.project:
            self.projects[event.project] += 1
        if event.branch:
            self.branches[event.branch] += 1
        if event.skill:
            self.skills[event.skill] += 1
        if event.mcp_tool:
            self.mcp[event.mcp_tool] += 1
        if event.model:
            self.models[event.model] += 1
        if event.tokens:
            for key, value in event.tokens.items():
                self.tokens[key] += value

        if event.kind == "user":
            self.user_messages += 1
            self._ingest_prompt(event)
        elif event.kind == "assistant":
            self.assistant_messages += 1
        elif event.kind == "tool":
            self.tool_calls += 1
            if event.tool:
                self.tools[event.tool] += 1
            if event.session and event.session in self.sessions:
                self.sessions[event.session].tool_calls += 1
        elif event.kind == "meta" and event.text is not None:
            self._ingest_prompt(event)

    def _ingest_prompt(self, event: Event) -> None:
        text = event.text
        if not text:
            return
        if looks_machine_generated(text):
            self.machine_prompts_skipped += 1
            return
        self.prompts_scanned += 1
        # What the operator *said* is a claim about a person, so it is drawn
        # only from turns a person actually typed.
        if not event.interactive:
            self.automated_prompts_skipped += 1
            return
        self.interactive_prompts += 1
        if is_correction(text):
            self.corrections += 1
        cleaned = clean_prompt_text(text)
        # Below a few words there is no phrase left worth counting.
        if len(cleaned.split()) < 4:
            return
        # An identical prompt repeated hundreds of times is a script's template,
        # not something the operator kept saying. Count each distinct prompt
        # once; a phrase that is genuinely characteristic still recurs across
        # *different* prompts, which is what the card is trying to surface.
        digest = hash(cleaned)
        if digest in self._prompt_digests:
            self.template_prompts_skipped += 1
            return
        self._prompt_digests.add(digest)
        self.phrases.add(cleaned)
        if self.first_prompt is None or event.ts < _dt.datetime.fromisoformat(
            self.first_prompt["at"]
        ):
            self.first_prompt = {
                "at": event.ts.isoformat(),
                "text": text,
                "session": event.session,
                "source": event.source,
                "project": event.project,
            }

    # -- derived measures --------------------------------------------------

    @property
    def session_minutes(self) -> list[float]:
        """Lengths of substantive sessions only. See :data:`MIN_SESSION_EVENTS`."""
        return [
            acc.active_seconds / 60
            for acc in self.sessions.values()
            if acc.active_seconds > 0 and acc.messages >= MIN_SESSION_EVENTS
        ]

    @property
    def substantive_sessions(self) -> int:
        return sum(1 for a in self.sessions.values() if a.messages >= MIN_SESSION_EVENTS)

    def median_session_minutes(self) -> float | None:
        values = self.session_minutes
        return round(median(values), 2) if values else None

    def total_active_minutes(self) -> float:
        return round(sum(acc.active_seconds for acc in self.sessions.values()) / 60, 1)

    def longest_session(self) -> dict[str, Any] | None:
        if not self.sessions:
            return None
        sid, acc = max(self.sessions.items(), key=lambda kv: kv[1].active_seconds)
        if acc.active_seconds <= 0:
            return None
        return {
            "session": sid,
            "active_minutes": round(acc.active_seconds / 60, 1),
            "started": acc.first.isoformat(),
            "ended": acc.last.isoformat(),
            "messages": acc.messages,
            "tool_calls": acc.tool_calls,
            "project": acc.project,
            "branch": acc.branch,
            "source": acc.source,
        }

    def hardest_session(self) -> dict[str, Any] | None:
        """The session that took the most tool calls to get through."""
        if not self.sessions:
            return None
        sid, acc = max(self.sessions.items(), key=lambda kv: kv[1].tool_calls)
        if acc.tool_calls == 0:
            return None
        return {
            "session": sid, "tool_calls": acc.tool_calls, "messages": acc.messages,
            "project": acc.project, "branch": acc.branch,
            "started": acc.first.isoformat(),
        }

    def tool_family_counts(self) -> tuple[int, int, int]:
        build = sum(n for t, n in self.tools.items() if t in BUILD_TOOLS)
        explore = sum(n for t, n in self.tools.items() if t in EXPLORE_TOOLS)
        delegate = sum(n for t, n in self.tools.items() if t in DELEGATE_TOOLS)
        return build, explore, delegate

    def personality_signals(self) -> dict[str, float | None]:
        build, explore, delegate = self.tool_family_counts()
        surveyed = build + explore
        sessions = len(self.sessions)
        return {
            "build_ratio": (build / surveyed) if surveyed else None,
            "median_session_minutes": self.median_session_minutes(),
            "delegations_per_session": (delegate / sessions) if sessions else None,
            "correction_rate": (self.corrections / self.interactive_prompts)
            if self.interactive_prompts
            else None,
        }

    def night_share(self) -> float | None:
        total = sum(self.by_hour)
        if not total:
            return None
        return round(sum(self.by_hour[h] for h in NIGHT_HOURS) / total, 4)

    # -- output ------------------------------------------------------------

    def rhythm(self) -> dict[str, Any]:
        busiest_hour = max(range(24), key=lambda h: self.by_hour[h]) if sum(self.by_hour) else None
        busiest_day = (
            max(range(7), key=lambda d: self.by_weekday[d]) if sum(self.by_weekday) else None
        )
        quietest_day = (
            min(range(7), key=lambda d: self.by_weekday[d]) if sum(self.by_weekday) else None
        )
        return {
            "by_hour": list(self.by_hour),
            "by_weekday": {WEEKDAYS[i]: n for i, n in enumerate(self.by_weekday)},
            "by_month": dict(sorted(self.by_month.items())),
            "active_days": len(self.active_days),
            "longest_streak": longest_streak(self.active_days),
            "night_share": self.night_share(),
            "busiest_hour": busiest_hour,
            "busiest_weekday": WEEKDAYS[busiest_day] if busiest_day is not None else None,
            "quietest_weekday": WEEKDAYS[quietest_day] if quietest_day is not None else None,
        }

    def totals(self) -> dict[str, Any]:
        return {
            "events": self._events,
            "sessions": len(self.sessions),
            "substantive_sessions": self.substantive_sessions,
            "min_session_events": MIN_SESSION_EVENTS,
            "user_messages": self.user_messages,
            "assistant_messages": self.assistant_messages,
            "tool_calls": self.tool_calls,
            "active_minutes": self.total_active_minutes(),
            "median_session_minutes": self.median_session_minutes(),
            "tokens": dict(self.tokens) or None,
            "by_source": dict(self.by_source),
        }

    def rankings(self) -> dict[str, Any]:
        return {
            "tools": _rank(self.tools),
            "skills": _rank(self.skills),
            "models": _rank(self.models),
            "projects": _rank(self.projects),
            "branches": _rank(self.branches),
            "mcp": _rank(self.mcp),
        }

    def moments(self) -> dict[str, Any]:
        return {
            "first_prompt": self.first_prompt,
            "longest_session": self.longest_session(),
            "hardest_session": self.hardest_session(),
            "top_phrases": self.phrases.top(),
            "phrase_coverage": {
                "prompts_scanned": self.phrases.prompts_seen,
                "words_scanned": self.phrases.words_seen,
                "word_budget": self.phrases.word_budget,
                "exhausted": self.phrases.exhausted,
                "machine_prompts_skipped": self.machine_prompts_skipped,
                "duplicate_prompts_skipped": self.template_prompts_skipped,
                "automated_prompts_skipped": self.automated_prompts_skipped,
                "interactive_prompts": self.interactive_prompts,
                "distinct_prompts": len(self._prompt_digests),
            },
            "correction_rate": round(self.corrections / self.interactive_prompts, 4)
            if self.interactive_prompts
            else None,
        }
