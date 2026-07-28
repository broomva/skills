#!/usr/bin/env python3
"""usage — measure which skills are ACTUALLY invoked, and rank the coverage gap.

Eval coverage is only worth what it covers. The BRO-2005 pilot picked `checkit`
for trace availability and it turned out to be our LEAST-used skill (1 invocation
in 1061 sessions) while `autonomous` (72) and `handoff` (31) had none. This
script makes "which skills do we actually use" a measurement instead of a guess,
so the next coverage decision is ranked by evidence.

Source of truth is the raw session transcripts, not the conversation-bridge logs:
the bridge writes SUMMARIES, which do not record tool calls at all (a scan of
1379 bridge logs found 7 invocations; the transcripts hold 163).

TWO CONTAMINATION TRAPS, both of which materially change the ranking:

1. Workflow subagent artifacts (`agent-*.jsonl`, `journal.jsonl`) sit in the same
   tree and match the same pattern — but an agent merely DISCUSSING a skill name
   in a prompt or result is not an invocation. Including them inflated a long
   tail of ~34 skills to a uniform "4 invocations / 3 sessions". Only UUID-named
   transcripts are real interactive sessions.
2. Vendored/plugin skills are invoked but not ours to edit (`npx skills update`
   overwrites them). They are reported separately, never mixed into the ranking.

Usage:
    python3 scripts/skill_evals/usage.py                 # ranked table + coverage gap
    python3 scripts/skill_evals/usage.py --json          # machine-readable
    python3 scripts/skill_evals/usage.py --top 10
    python3 scripts/skill_evals/usage.py --uncovered     # only skills lacking evals

Pure stdlib. Read-only. No network.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

DEFAULT_TRANSCRIPT_ROOT = Path.home() / ".claude" / "projects"
DEFAULT_SKILLS_ROOT = Path(__file__).resolve().parents[2] / "skills"

# A real interactive session transcript is UUID-named. `agent-<hex>.jsonl` and
# `journal.jsonl` are workflow subagent artifacts — see trap 1 in the docstring.
_SESSION_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.jsonl$")

# Matched against raw bytes: these files are large and mostly irrelevant.
_SKILL_RE = re.compile(rb'"skill"\s*:\s*"([a-z0-9][a-z0-9._-]*)"')


def is_session_transcript(name: str) -> bool:
    """True only for a real interactive session transcript.

    The whole point of this predicate — a workflow artifact that merely mentions
    a skill name is not evidence anyone invoked it.
    """
    return bool(_SESSION_RE.match(name))


def owned_skills(skills_root: Path) -> dict[str, str]:
    """{skill name -> repo-relative dir} for every skill this repo owns."""
    out: dict[str, str] = {}
    if not skills_root.is_dir():
        return out
    for p in skills_root.rglob("SKILL.md"):
        parts = set(p.parts)
        if ".venv" in parts or "node_modules" in parts:
            continue
        try:
            rel = p.parent.relative_to(skills_root.parent)
        except ValueError:
            rel = p.parent
        out[p.parent.name] = str(rel)
    return out


def has_evals(skills_root: Path, rel_dir: str) -> bool:
    """True when the skill ships a non-empty prompt set.

    Presence of the directory is NOT coverage — that exact conflation is what
    made `skillify_check.py` step 5 overstate our eval coverage 5x (BRO-2009).
    """
    prompts = skills_root.parent / rel_dir / "evals" / "prompts.json"
    if not prompts.is_file():
        return False
    try:
        data = json.loads(prompts.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(isinstance(data, dict) and data.get("cases"))


def scan(transcript_root: Path) -> tuple[Counter, dict[str, set], int]:
    """Count Skill invocations across real session transcripts only."""
    counts: Counter = Counter()
    sessions: dict[str, set] = defaultdict(set)
    scanned = 0
    if not transcript_root.is_dir():
        return counts, sessions, scanned
    for f in transcript_root.rglob("*.jsonl"):
        if not is_session_transcript(f.name):
            continue
        scanned += 1
        try:
            blob = f.read_bytes()
        except OSError:
            continue
        if b'"skill"' not in blob:  # cheap reject before the regex
            continue
        for m in _SKILL_RE.finditer(blob):
            name = m.group(1).decode("utf-8", "replace")
            counts[name] += 1
            sessions[name].add(f.name)
    return counts, sessions, scanned


def build_report(transcript_root: Path, skills_root: Path) -> dict:
    counts, sessions, scanned = scan(transcript_root)
    owned = owned_skills(skills_root)
    ranked, external = [], []
    for name, n in counts.most_common():
        row = {"skill": name, "invocations": n, "sessions": len(sessions[name])}
        if name in owned:
            row["path"] = owned[name]
            row["has_evals"] = has_evals(skills_root, owned[name])
            ranked.append(row)
        else:
            external.append(row)
    total = sum(r["invocations"] for r in ranked)
    covered = sum(r["invocations"] for r in ranked if r["has_evals"])
    return {
        "transcripts_scanned": scanned,
        "owned_skills": len(owned),
        "owned_ever_invoked": len(ranked),
        "owned_invocations": total,
        # The number that matters: not "how many skills have evals" but "what
        # share of actual usage is covered". One eval on a skill nobody invokes
        # is 0% by this measure, which is the honest reading.
        "invocation_coverage": round(covered / total, 4) if total else 0.0,
        "skills_with_evals": sum(1 for r in ranked if r["has_evals"]),
        "ranked": ranked,
        "external_not_ours": external[:10],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--transcripts", type=Path, default=DEFAULT_TRANSCRIPT_ROOT)
    ap.add_argument("--skills-root", type=Path, default=DEFAULT_SKILLS_ROOT)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--uncovered", action="store_true", help="only skills lacking a prompt set")
    args = ap.parse_args(argv)

    rep = build_report(args.transcripts, args.skills_root)
    if args.as_json:
        print(json.dumps(rep, indent=2))
        return 0

    if not rep["transcripts_scanned"]:
        print(f"[usage] no session transcripts under {args.transcripts}", file=sys.stderr)
        return 2

    rows = [r for r in rep["ranked"] if not args.uncovered or not r["has_evals"]]
    print(f"[usage] {rep['transcripts_scanned']} session transcripts · "
          f"{rep['owned_invocations']} invocations of {rep['owned_ever_invoked']}"
          f"/{rep['owned_skills']} owned skills")
    print(f"[usage] invocation-weighted eval coverage: {rep['invocation_coverage']:.1%} "
          f"({rep['skills_with_evals']} skill(s) with a prompt set)\n")
    print(f"{'#':>3} {'skill':28} {'inv':>5} {'sess':>5}  evals  path")
    print("-" * 78)
    for i, r in enumerate(rows[: args.top], 1):
        print(f"{i:>3} {r['skill']:28} {r['invocations']:>5} {r['sessions']:>5}"
              f"  {'yes' if r['has_evals'] else ' NO':>5}  {r['path']}")
    if rep["external_not_ours"]:
        ext = ", ".join(f"{r['skill']}({r['invocations']})" for r in rep["external_not_ours"][:6])
        print(f"\nused but NOT ours (vendored/plugin — edits get overwritten): {ext}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
