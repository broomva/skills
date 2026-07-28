#!/usr/bin/env python3
"""listing — does a skill's description actually REACH the model? (BRO-2014)

The whole trigger-eval arc rests on an assumption nobody had checked: that the
description we author is the description the model sees. It usually is not.

Claude Code injects the skill roster as a ``skill_listing`` attachment whose
rendered ``content`` is capped. Measured on this machine across 1,199 listings in
1,039 session transcripts, the largest listing ever delivered is 39,013 characters
— and our model-invocable skills carry 101,654 characters of trigger surface, 2.6x
that floor. So the harness rations: the skills that fit render as
``- name: <description>``, and the rest render as a bare ``- name`` line with **no
trigger text at all**.

A skill whose description never reaches the model can never trigger, and nothing in
the stack reported it. In the session that produced this module: 146 skills, 34
full, 2 truncated, **110 bare (75.3%)**. The bstack primitives are among the worst
hit — ``role-x`` (P17), ``persist`` (P12), ``cross-review`` (P20),
``orchestration`` (P19) and ``bookkeeping`` (P6) all arrived BARE, while ``kg`` and
``dogfood`` arrived truncated mid-sentence. Which skills win is not stable between
sessions, so this is not a fixed set to design around.

WHAT THIS MODULE IS, AND IS NOT
-------------------------------
It is a **detector**. It reads the attachment the model actually received and
reports, per skill, whether the description arrived FULL, TRUNCATED, or BARE.

It is deliberately NOT a CI gate. Its input is one machine's
``~/.claude/projects``, which does not exist on a runner, so a CI check over it
would be green by construction — the precise vacuity this arc exists to hunt. It
belongs in ``bstack doctor`` as an advisory section, next to P7 freshness.

Nor does it choose winners: nothing in our stack can. The only controllable
variable is total mass, which is what ``--budget`` ranks.

    python3 scripts/skill_evals/listing.py              # latest listing, classified
    python3 scripts/skill_evals/listing.py --budget     # mass vs cap, trim candidates
    python3 scripts/skill_evals/listing.py --calibrate  # re-derive the caps from disk
    python3 scripts/skill_evals/listing.py --json

Pure stdlib. Read-only. No network.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from skill_evals.runner import parse_frontmatter_description  # noqa: E402
from skill_evals.usage import is_session_transcript  # noqa: E402

DEFAULT_TRANSCRIPT_ROOT = Path.home() / ".claude" / "projects"
DEFAULT_SKILL_ROOTS = (
    Path.home() / ".claude" / "skills",
    Path.home() / ".agents" / "skills",
)

#: The largest listing this machine has actually been served, in characters.
#:
#: A LOWER BOUND on the cap, not the cap. The true limit is Claude Code's and is not
#: published; what is measurable is the biggest listing that ever arrived. Naming it
#: for what it is matters, because the conclusion does not depend on the exact
#: number: our trigger surface exceeds even this floor by more than 2x, and three
#: quarters of skills arrive with no description either way.
#:
#: OBSERVED, and re-derivable: ``--calibrate`` recomputes it over the local corpus
#: and FAILS LOUD when the observed maximum exceeds it. That is not decoration — the
#: first calibration run rejected this constant's original value (30,000, taken from
#: a smaller sample) against an observed 39,013, which is exactly the silent-staleness
#: this mechanism exists to prevent. The corpus also still contains an older
#: ~8,000-char regime, so the limit demonstrably moves between releases.
BUDGET_CHARS = 39_013

#: Per-skill cap. A description longer than this renders truncated, terminated by a
#: literal U+2026. Also observed rather than assumed.
PER_SKILL_CHARS = 1_536

ELLIPSIS = "…"

FULL = "FULL"
TRUNCATED = "TRUNCATED"
BARE = "BARE"

#: A listing entry opens a line. The NAME is not matched by a character class on
#: purpose — see :func:`_entry_name`.
_ENTRY_RE = re.compile(r"^- (.+)$")


@dataclass(frozen=True)
class Listing:
    """One ``skill_listing`` attachment, as the model received it."""

    names: tuple[str, ...]
    content: str
    source: str = ""
    is_initial: bool = False

    @property
    def skill_count(self) -> int:
        return len(self.names)

    @property
    def content_chars(self) -> int:
        return len(self.content)


@dataclass
class Classification:
    """Per-skill delivery state, plus the totals worth reporting."""

    states: dict[str, str] = field(default_factory=dict)
    unparsed: list[str] = field(default_factory=list)

    def count(self, state: str) -> int:
        return sum(1 for v in self.states.values() if v == state)

    @property
    def bare(self) -> list[str]:
        return sorted(n for n, v in self.states.items() if v == BARE)

    @property
    def truncated(self) -> list[str]:
        return sorted(n for n, v in self.states.items() if v == TRUNCATED)

    def to_dict(self) -> dict[str, Any]:
        total = len(self.states)
        return {
            "skills": total,
            "full": self.count(FULL),
            "truncated": self.count(TRUNCATED),
            "bare": self.count(BARE),
            "bare_share": round(self.count(BARE) / total, 4) if total else 0.0,
            "bare_skills": self.bare,
            "truncated_skills": self.truncated,
            "unparsed": self.unparsed,
        }


# ---------------------------------------------------------------------------
# reading the attachment
# ---------------------------------------------------------------------------


def _find_attachment(obj: Any) -> dict[str, Any] | None:
    """Depth-first search for a ``skill_listing`` attachment anywhere in a record."""
    if isinstance(obj, dict):
        if obj.get("type") == "skill_listing" and isinstance(obj.get("content"), str):
            return obj
        for value in obj.values():
            found = _find_attachment(value)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_attachment(value)
            if found is not None:
                return found
    return None


def listings_in(path: Path) -> list[Listing]:
    """Every listing attachment in one transcript, in file order."""
    out: list[Listing] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    if '"skill_listing"' not in text:  # cheap reject before parsing 100k lines
        return out
    for line in text.splitlines():
        if '"skill_listing"' not in line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        att = _find_attachment(record)
        if att is None:
            continue
        names = att.get("names")
        out.append(
            Listing(
                names=tuple(str(n) for n in names) if isinstance(names, list) else (),
                content=str(att.get("content") or ""),
                source=path.name,
                is_initial=bool(att.get("isInitial")),
            )
        )
    return out


def iter_transcripts(root: Path) -> Iterable[Path]:
    """Real interactive sessions only.

    Reuses :func:`skill_evals.usage.is_session_transcript` rather than
    re-implementing it: ``agent-*.jsonl`` and ``journal.jsonl`` are workflow
    subagent artifacts, and counting them once already inflated a whole ranking.
    """
    if not root.is_dir():
        return []
    return (p for p in root.rglob("*.jsonl") if is_session_transcript(p.name))


def latest_listing(root: Path = DEFAULT_TRANSCRIPT_ROOT) -> Listing | None:
    """The most recently written session's listing — what the model sees *now*."""
    for path in sorted(iter_transcripts(root), key=lambda p: -p.stat().st_mtime):
        found = listings_in(path)
        if found:
            return found[-1]
    return None


# ---------------------------------------------------------------------------
# THE ROOT PREDICATE
# ---------------------------------------------------------------------------


def _entry_name(body: str, known: Iterable[str]) -> str | None:
    """The skill this entry belongs to, by LONGEST-PREFIX match against ``names``.

    Never a regex character class over the name. Two reasons, both load-bearing:

    * plugin skills are named ``paper-desktop:code-to-design``, so ``:`` has to be
      inside any plausible name class — and then the class greedily swallows the
      ``name: description`` delimiter and every described skill reads as bare. That
      exact bug produced a false "everything is bare" reading in the investigation
      that preceded this module;
    * a description may itself contain a line starting with ``- ``. Anchoring on the
      attachment's own ``names`` array means such a line is treated as continuation
      text rather than as a new entry, because it matches no known skill.
    """
    best: str | None = None
    for name in known:
        if body == name or body.startswith(name + ":"):
            if best is None or len(name) > len(best):
                best = name
    return best


def parse_entries(listing: Listing) -> tuple[dict[str, str], list[str]]:
    """``({skill: text after its name}, unparsed lines)``."""
    known = set(listing.names)
    entries: dict[str, str] = {}
    unparsed: list[str] = []
    current: str | None = None
    buf: list[str] = []

    for line in listing.content.splitlines():
        match = _ENTRY_RE.match(line)
        body = match.group(1) if match else ""
        name = _entry_name(body, known) if match else None
        if name is not None:
            if current is not None:
                entries[current] = "\n".join(buf)
            current = name
            buf = [body[len(name):]]
        elif current is not None:
            buf.append(line)
        elif line.strip():
            unparsed.append(line[:120])
    if current is not None:
        entries[current] = "\n".join(buf)
    return entries, unparsed


def entry_state(text: str) -> str:
    """FULL / TRUNCATED / BARE for the text that followed a skill's name."""
    body = text.lstrip(":").strip()
    if not body:
        return BARE
    return TRUNCATED if body.endswith(ELLIPSIS) else FULL


def classify(listing: Listing) -> Classification:
    """Per-skill delivery state for one listing.

    Every name in the attachment is accounted for. A name present in ``names`` but
    absent from the rendered content is BARE by definition — the model got the name
    and nothing else, which is the state this module exists to surface.
    """
    entries, unparsed = parse_entries(listing)
    states = {name: entry_state(entries.get(name, "")) for name in listing.names}
    return Classification(states=states, unparsed=unparsed)


# ---------------------------------------------------------------------------
# the only controllable variable: total mass
# ---------------------------------------------------------------------------


def _frontmatter_field(text: str, *keys: str) -> str:
    """A scalar frontmatter field, taking the first of *keys* that is present.

    Several spellings are accepted because authors use both: the field on disk is
    ``when_to_use`` (4 occurrences), but ``when-to-use`` is the shape a reader
    expects from the hyphenated ``disable-model-invocation`` next to it. Reading
    only one spelling silently measures zero for the other.
    """
    wanted = {k.lower() for k in keys}
    for line in text.splitlines():
        if line[:1].isspace() or ":" not in line:
            continue
        if line.split(":", 1)[0].strip().lower() in wanted:
            return line.split(":", 1)[1].strip()
    return ""


@dataclass(frozen=True)
class SkillMass:
    name: str
    path: str
    description_chars: int
    when_to_use_chars: int

    @property
    def effective(self) -> int:
        """Characters this skill costs in the listing.

        ``when_to_use`` is included because it is rendered alongside the
        description. Counting the description alone undercounts the model-visible
        surface today and would drift further as more skills adopt the field —
        measuring the wrong quantity is how a budget report becomes decoration.
        """
        overhead = len(f"- {self.name}: ") + 1
        extra = (self.when_to_use_chars + 3) if self.when_to_use_chars else 0
        return overhead + self.description_chars + extra


def skill_masses(roots: Iterable[Path]) -> list[SkillMass]:
    """Effective listing mass for every model-invocable skill under *roots*."""
    seen: dict[str, SkillMass] = {}
    for root in roots:
        if not Path(root).is_dir():
            continue
        for md in sorted(Path(root).rglob("SKILL.md")):
            parts = set(md.parts)
            if ".venv" in parts or "node_modules" in parts:
                continue
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # A skill that opts out of model invocation costs nothing in the
            # listing — counting it would overstate the overshoot.
            if _frontmatter_field(text, "disable-model-invocation", "disable_model_invocation").lower() == "true":
                continue
            name = md.parent.name
            if name in seen:
                continue
            seen[name] = SkillMass(
                name=name,
                path=str(md.parent),
                description_chars=len(parse_frontmatter_description(text)),
                when_to_use_chars=len(_frontmatter_field(text, "when_to_use", "when-to-use")),
            )
    return sorted(seen.values(), key=lambda s: -s.effective)


def budget_report(roots: Iterable[Path] = DEFAULT_SKILL_ROOTS) -> dict[str, Any]:
    masses = skill_masses(roots)
    total = sum(m.effective for m in masses)
    return {
        "skills": len(masses),
        "effective_mass": total,
        "largest_observed_listing_chars": BUDGET_CHARS,
        "budget": BUDGET_CHARS,
        "overshoot": round(total / BUDGET_CHARS, 2) if BUDGET_CHARS else 0.0,
        "affordable_mean_chars": round(BUDGET_CHARS / len(masses)) if masses else 0,
        "over_per_skill_cap": [m.name for m in masses if m.effective > PER_SKILL_CHARS],
        "heaviest": [
            {"skill": m.name, "chars": m.effective, "path": m.path} for m in masses[:15]
        ],
    }


# ---------------------------------------------------------------------------
# calibration — the constants are measurements, and must stay measurements
# ---------------------------------------------------------------------------


def calibrate(root: Path = DEFAULT_TRANSCRIPT_ROOT) -> dict[str, Any]:
    """Re-derive the caps from the local corpus.

    A constant copied from one day's observation rots the moment the harness
    changes. This reports the observed maxima and whether either constant is now
    too low — the corpus already shows an older ~8,000-char regime alongside the
    current one, so the cap demonstrably moves between releases.
    """
    max_content = 0
    max_desc = 0
    listings = 0
    transcripts = 0
    for path in iter_transcripts(root):
        found = listings_in(path)
        if not found:
            continue
        transcripts += 1
        for listing in found:
            listings += 1
            max_content = max(max_content, listing.content_chars)
            entries, _ = parse_entries(listing)
            for text in entries.values():
                body = text.lstrip(":").strip()
                max_desc = max(max_desc, len(body))
    return {
        "transcripts_with_a_listing": transcripts,
        "listings": listings,
        "observed_max_content_chars": max_content,
        "declared_budget_chars": BUDGET_CHARS,
        "budget_constant_is_stale": max_content > BUDGET_CHARS,
        "observed_max_description_chars": max_desc,
        "declared_per_skill_chars": PER_SKILL_CHARS,
        "per_skill_constant_is_stale": max_desc > PER_SKILL_CHARS,
    }


# ---------------------------------------------------------------------------
# red conditions
# ---------------------------------------------------------------------------


def red_conditions(cls: Classification, budget: dict[str, Any]) -> list[str]:
    """What a reader should act on. Ordered by how directly each blocks triggering."""
    out: list[str] = []
    if cls.bare:
        out.append(
            f"R1 {len(cls.bare)} of {len(cls.states)} skills reached the model as a BARE "
            f"name with no description — they cannot be triggered by description at all"
        )
    if budget["effective_mass"] > budget["budget"]:
        out.append(
            f"R2 trigger surface is {budget['effective_mass']:,} chars against a "
            f"{budget['budget']:,}-char largest-observed listing ({budget['overshoot']}x) — "
            "the harness is rationing, and which skills win is not stable between sessions"
        )
    if budget["over_per_skill_cap"]:
        out.append(
            f"R3 {len(budget['over_per_skill_cap'])} skill(s) exceed the {PER_SKILL_CHARS}-char "
            f"per-skill cap and render truncated mid-sentence: "
            f"{', '.join(budget['over_per_skill_cap'][:6])}"
        )
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--transcripts", type=Path, default=DEFAULT_TRANSCRIPT_ROOT)
    ap.add_argument("--skill-root", type=Path, action="append", dest="skill_roots")
    ap.add_argument("--budget", action="store_true", help="mass vs cap, and the heaviest skills")
    ap.add_argument("--calibrate", action="store_true", help="re-derive the caps from the corpus")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args(argv)
    roots = args.skill_roots or list(DEFAULT_SKILL_ROOTS)

    if args.calibrate:
        cal = calibrate(args.transcripts)
        print(json.dumps(cal, indent=2) if args.as_json else "\n".join(
            f"  {k:34}{v}" for k, v in cal.items()))
        # Fail loud rather than silently mis-flagging every skill against a stale cap.
        return 1 if (cal["budget_constant_is_stale"] or cal["per_skill_constant_is_stale"]) else 0

    listing = latest_listing(args.transcripts)
    budget = budget_report(roots)

    if listing is None:
        if args.as_json:
            print(json.dumps({"listing": None, "budget": budget}, indent=2))
            return 0
        print(f"[listing] no skill_listing attachment found under {args.transcripts}",
              file=sys.stderr)
        print(f"[listing] budget only: {budget['effective_mass']:,} chars of trigger "
              f"surface against a {budget['budget']:,} cap ({budget['overshoot']}x)")
        return 2

    cls = classify(listing)
    reds = red_conditions(cls, budget)

    if args.as_json:
        print(json.dumps({
            "listing": {"source": listing.source, "skills": listing.skill_count,
                        "content_chars": listing.content_chars},
            "classification": cls.to_dict(),
            "budget": budget,
            "red_conditions": reds,
        }, indent=2))
        return 0

    d = cls.to_dict()
    print(f"[listing] {listing.source} · {listing.skill_count} skills · "
          f"{listing.content_chars:,} chars rendered (cap ~{BUDGET_CHARS:,})")
    print(f"[listing] delivered: {d['full']} full · {d['truncated']} truncated · "
          f"{d['bare']} BARE ({d['bare_share']:.1%})\n")

    if args.budget:
        print(f"{'skill':38}{'chars':>8}")
        print("-" * 46)
        for row in budget["heaviest"][: args.top]:
            print(f"{row['skill'][:37]:38}{row['chars']:>8}")
        print("-" * 46)
        print(f"{'TOTAL':38}{budget['effective_mass']:>8}  vs {budget['budget']} cap "
              f"({budget['overshoot']}x)")
        print(f"\naffordable mean per skill at this count: "
              f"{budget['affordable_mean_chars']} chars")
        print("Trimming the heaviest few cannot reach the cap — the lever is the skill "
              "COUNT, not description length.")
    elif d["bare"]:
        shown = d["bare_skills"][: args.top]
        print("reached the model as a BARE name (cannot trigger by description):")
        for name in shown:
            print(f"  - {name}")
        if len(d["bare_skills"]) > len(shown):
            print(f"  … and {len(d['bare_skills']) - len(shown)} more")

    for line in reds:
        print(f"\n[listing] {line}", file=sys.stderr)
    # Advisory by design: this reads one machine's transcripts, so a non-zero exit
    # wired into CI would be a gate on a file that does not exist there.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
