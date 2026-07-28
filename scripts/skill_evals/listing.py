#!/usr/bin/env python3
"""listing — does a skill's description actually REACH the model? (BRO-2014)

The whole trigger-eval arc rests on an assumption nobody had checked: that the
description we author is the description the model sees. It usually is not.

Claude Code injects the skill roster as a ``skill_listing`` attachment whose
rendered ``content`` is capped. Measured on this machine across 1,199 listings in
1,039 session transcripts, the largest listing ever delivered is 39,013 characters
— and the 124 roster skills present on disk carry 94,800 characters of trigger
surface, 2.4x that floor (itself a lower bound: 22 more listed names are CLI
built-ins whose descriptions are unmeasurable). So the harness rations: the skills
that fit render as
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
    #: How many entries the parser actually READ out of the content. Distinct from
    #: len(states), which defaults every name in the attachment to BARE and is
    #: therefore non-empty whenever the roster is — the reason R0 could not see a
    #: total parse failure.
    parsed_entries: int = 0

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
            "parsed_entries": self.parsed_entries,
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
    """The most recent session's FULL roster listing — what the model sees now.

    Not simply the last attachment in the newest transcript. A session emits an
    initial listing carrying the whole roster and then INCREMENTAL ones carrying a
    single skill, so taking the last attachment routinely classifies a 1-skill
    listing and reports ``0 BARE (0.0%)`` — a clean bill of health for a machine
    where three quarters of the roster is bare. That was reproduced on a real
    transcript from this machine, and hit by accident during review, which is how
    reachable it is.

    Prefers ``isInitial``; falls back to the largest by skill count, so a transcript
    whose attachments predate that flag still yields the full roster.
    """
    for path in sorted(iter_transcripts(root), key=lambda p: -p.stat().st_mtime):
        found = listings_in(path)
        if not found:
            continue
        initial = [lst for lst in found if lst.is_initial]
        return max(initial or found, key=lambda lst: lst.skill_count)
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
    return Classification(states=states, unparsed=unparsed, parsed_entries=len(entries))


# ---------------------------------------------------------------------------
# the only controllable variable: total mass
# ---------------------------------------------------------------------------


def _frontmatter_field(text: str, *keys: str) -> str:
    """A frontmatter field, taking the first of *keys* that is present.

    Scoped to the FRONTMATTER block, and block-scalar aware. The first version was
    neither, and failed in both directions on real skills:

    * it scanned the whole file, so ``design-taste-frontend`` — which has no
      ``when_to_use`` in its frontmatter but does have the string on line 872 of its
      BODY — was charged 110 phantom characters;
    * it took everything after the colon, so ``when_to_use: |`` followed by a
      317-character block scalar (``p9``, ``swapit``, ``procurer`` all use this)
      measured as the single character ``|``.

    Several spellings are accepted because authors use both ``when_to_use`` and
    ``when-to-use``; reading one silently measures zero for the other.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return ""
    block = lines[1:end]

    wanted = {k.lower() for k in keys}
    for idx, line in enumerate(block):
        if line[:1].isspace() or ":" not in line:
            continue
        if line.split(":", 1)[0].strip().lower() not in wanted:
            continue
        rest = line.split(":", 1)[1].strip()
        if rest not in (">", "|", ">-", "|-", ">+", "|+"):
            return rest
        # Block scalar: everything indented under the key, until dedent.
        collected: list[str] = []
        for cont in block[idx + 1:]:
            if not cont.strip():
                collected.append("")
                continue
            if not cont[:1].isspace():
                break
            collected.append(cont.strip())
        return "\n".join(collected).strip()
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
    """Effective listing mass for every model-invocable skill under *roots*.

    TOP-LEVEL directories only, enumerated with ``iterdir``. Not ``rglob``, and the
    difference is not cosmetic: ``Path.rglob`` does not descend into symlinked
    directories, and a skill install root is almost entirely symlinks — 125 of the
    129 entries under ``~/.claude/skills`` on this machine. ``rglob`` finds **3**
    SKILL.md files there; ``iterdir`` finds **128**.

    The first version of this function used ``rglob`` and therefore measured a
    population that was 60% skills which have never appeared in any listing, while
    missing 84 of the 146 the roster actually carries. It reported ``kg`` and
    ``dogfood`` as TRUNCATED from the transcript in the same run that reported
    ``over_per_skill_cap == []``, because those two are symlinks it could not see —
    the R3 check was silent on the only two confirmed truncations in the corpus.
    That is the install-dir-mistaken-for-source-tree vacuity, in a module written to
    hunt vacuity.

    Nested bundles (``<root>/<skill>/.skills/<sub>``) are deliberately NOT walked:
    they are not roster entries and counting them inflates the total.
    """
    seen: dict[str, SkillMass] = {}
    for root in roots:
        if not Path(root).is_dir():
            continue
        for entry in sorted(Path(root).iterdir()):
            md = entry / "SKILL.md"
            # is_file() resolves through the symlink, which is the whole point.
            if not md.is_file():
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


def budget_report(
    roots: Iterable[Path] = DEFAULT_SKILL_ROOTS, roster: Iterable[str] | None = None
) -> dict[str, Any]:
    """Mass against the cap, scoped to the roster the harness actually lists.

    *roster* matters: a skill on disk that never appears in a listing costs nothing,
    so folding it into the total both overstates the overshoot and puts skills on the
    trim list whose removal would save nothing. The first version had no roster
    parameter at all and reported 369 skills against a 146-name roster — 60% of the
    mass from skills that have never been listed, while missing 84 that had.
    """
    masses = skill_masses(roots)
    listed = set(roster) if roster is not None else None
    if listed is not None:
        counted = [m for m in masses if m.name in listed]
        unlisted = [m for m in masses if m.name not in listed]
        missing = sorted(listed - {m.name for m in masses})
    else:
        counted, unlisted, missing = masses, [], []
    total = sum(m.effective for m in counted)
    # The DENOMINATOR is the roster, not the measurable subset. 22 of the 146 listed
    # names here are CLI built-ins that exist nowhere on disk, yet 13 of them arrived
    # FULL and consumed 6,404 of the 30,087 rendered chars — 21% of the delivered
    # listing, charged at zero mass. Dividing the cap by the measurable 124 gave an
    # affordable mean of 315 chars when the listing must fit 146 entries; an author
    # trimming to 315 on that guidance still overflows. The honest figure is 267.
    roster_size = len(listed) if listed is not None else len(counted)
    return {
        "skills": len(counted),
        "roster_size": roster_size,
        # A FLOOR, not a total: the unmeasurable built-ins add an unknown positive
        # amount, so the real overshoot is worse than what this reports.
        "effective_mass_is_a_floor": bool(missing),
        "on_disk_not_in_roster": len(unlisted),
        "in_roster_not_on_disk_count": len(missing),
        "in_roster_not_on_disk": missing[:20],
        "effective_mass": total,
        "largest_observed_listing_chars": BUDGET_CHARS,
        "budget": BUDGET_CHARS,
        "overshoot": round(total / BUDGET_CHARS, 2) if BUDGET_CHARS else 0.0,
        "affordable_mean_chars": round(BUDGET_CHARS / roster_size) if roster_size else 0,
        "over_per_skill_cap": [m.name for m in counted if m.effective > PER_SKILL_CHARS],
        "heaviest": [
            {"skill": m.name, "chars": m.effective, "path": m.path} for m in counted[:15]
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


def red_conditions(
    cls: Classification, budget: dict[str, Any], listing: Listing | None = None
) -> list[str]:
    """What a reader should act on. Ordered by how directly each blocks triggering."""
    out: list[str] = []
    # R0 first, because everything below it is only meaningful if the listing was
    # actually read. A listing that parses to zero entries reported "0 BARE (0.0%)"
    # with no red condition at all — for a 199-skill attachment where every line was
    # unreadable. Absence of parsed entries is not absence of bare skills; it is
    # absence of a measurement, and it has to say so.
    # Keyed on PARSED entries, not on len(states): classify() defaults every name in
    # the attachment to BARE, so states is non-empty whenever the roster is. The
    # first version tested `not cls.states`, which is true only for an EMPTY names
    # array — 2 of 1,203 real listings. On the reachable shape (Claude Code changes
    # the line format, so a populated 199-name listing parses to nothing) it reported
    # "199 of 199 BARE": the exact OPPOSITE diagnosis, with the disclaimer suppressed.
    if listing is not None and listing.content_chars > 0 and not cls.parsed_entries:
        out.append(
            f"R0 the listing rendered {listing.content_chars:,} chars but parsed to ZERO "
            f"entries ({len(cls.unparsed)} unreadable lines) — this report is not a "
            "measurement, and the counts below mean nothing"
        )
    # `>=`, not `>`: the canonical total-failure shape is exactly one unreadable line
    # per skill, so equality is the NORM for that failure, not an edge of it.
    elif cls.states and len(cls.unparsed) >= len(cls.states):
        out.append(
            f"R0 {len(cls.unparsed)} unreadable lines against only {len(cls.states)} parsed "
            "entries — the listing shape may have changed; treat the counts as suspect"
        )
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
    budget = budget_report(roots, roster=listing.names if listing else None)

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
    reds = red_conditions(cls, budget, listing)

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
        floor = " (a FLOOR)" if budget.get("effective_mass_is_a_floor") else ""
        print(f"{'TOTAL':38}{budget['effective_mass']:>8}{floor}  vs {budget['budget']} cap "
              f"({budget['overshoot']}x)")
        # Printed, not just in the JSON: a reader who cannot see that N listed skills
        # were dropped from the measurable set reads the total as complete.
        if budget.get("in_roster_not_on_disk_count"):
            names = ", ".join(budget["in_roster_not_on_disk"][:6])
            print(f"\n{budget['in_roster_not_on_disk_count']} listed skill(s) are NOT on "
                  f"disk (CLI built-ins) and consume budget we cannot measure: {names}…")
        print(f"\naffordable mean per ROSTER entry ({budget['roster_size']}): "
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
