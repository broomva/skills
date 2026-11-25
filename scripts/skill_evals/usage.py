#!/usr/bin/env python3
"""usage — measure which skills are ACTUALLY invoked, and rank the coverage gap.

Eval coverage is only worth what it covers. The BRO-2005 pilot picked `checkit`
for trace availability and it turned out to be our LEAST-used skill (1 invocation
in 1061 sessions) while `autonomous` (72) and `handoff` (31) had none. Those
counts saw only Skill tool calls; `checkit` is mostly TYPED, and with typed loads
counted it ranks second (trap 4 below, measured 2026-11-24). This script makes "which skills do we actually use" a measurement instead of a guess,
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

THREE MORE, found measuring the cost of a skill (BRO-4111):

3. The byte regex this module used counted ONE call two or three times. Claude
   Code writes a call's input twice on the same row (``input`` and
   ``wireToolInputs``), and any later text quoting ``{"skill": ...}`` matched too.
   A transcript with 2 Skill calls scored 5. Invocations are now read structurally:
   one per ``Skill`` tool_use id.
4. A skill the USER types (``/checkit``) never appears as a Skill tool call, so the
   regex never saw it. Typed loads show up as a ``<command-name>`` prompt followed
   by an ``isMeta`` row carrying "Base directory for this skill:". They are counted
   now, and every row says who chose the skill (``invoked_by``: agent or user).
5. One API response is split across several rows that repeat the same ``usage``.
   Summing rows multiplies the cost; responses are counted once per message id.

COST OF AN INVOCATION (the idea is from Uber's 2026-11-23 post on skill evals):
the WINDOW of an invocation runs from the skill load to the next human prompt or
the next skill load, whichever comes first. Its tokens are the summed ``usage`` of
the distinct API responses inside it: the model reading the skill, the turns that
follow and any tool calls in between. ``context_added`` is how much the total
input grew from the response before the load to the first one after it. Tokens,
not dollars: prices change and differ by model. A skill with no measurable window
reports ``cost: null``, never zeros. Claude Code transcripts only; Codex logs have
no Skill tool to anchor an invocation on.

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

# Cheap byte-level reject before parsing a file: no skill load can be in it otherwise.
_MARKERS = (re.compile(rb'"name"\s*:\s*"Skill"'), re.compile(rb"Base directory for this skill"))
_INTERRUPT = "[Request interrupted by user"
# User-role rows the harness writes on its own; not a person's prompt.
_INJECTED_PREFIXES = ("<task-notification>", "<local-command-stdout>", "<local-command-stderr>",
                      "This session is being continued from a previous conversation")
_LOAD_RE = re.compile(r"Base directory for this skill:\s*(\S+)")
_USAGE_FIELDS = ("input_tokens", "cache_creation_input_tokens",
                 "cache_read_input_tokens", "output_tokens")


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


def _message(row: dict) -> dict:
    msg = row.get("message")
    return msg if isinstance(msg, dict) else {}


def _text(row: dict) -> str:
    content = _message(row).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(b.get("text", "")) for b in content
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _is_human_prompt(row: dict) -> bool:
    """A turn a person started: typed text or an image, or an interrupt.

    Not a tool result, not an injected meta row, and not one of the user-role rows
    the harness writes on its own (measured 2026-11-24 over the corpus: task
    notifications, local command output, the post-compaction summary).
    """
    if row.get("type") != "user" or row.get("isMeta") or row.get("isSidechain"):
        return False
    content = _message(row).get("content")
    if isinstance(content, list):
        kinds = {b.get("type") for b in content if isinstance(b, dict)}
        if _INTERRUPT in _text(row):
            return True  # the person stopped the turn, whatever else the row carries
        if "tool_result" in kinds or not kinds & {"text", "image"}:
            return False
    elif not isinstance(content, str):
        return False
    return not _text(row).lstrip().startswith(_INJECTED_PREFIXES)


def _responses(rows: list[dict]) -> list[tuple[int, str, dict]]:
    """(first row index, message id, usage) once per real API response, in order.

    A response split across rows repeats its id and usage, so it is counted once.
    Rows the harness writes itself (model "<synthetic>") are not API responses.
    """
    seen: set[str] = set()
    out: list[tuple[int, str, dict]] = []
    for i, row in enumerate(rows):
        if row.get("type") != "assistant" or row.get("isSidechain"):
            continue
        msg = _message(row)
        mid, usage = msg.get("id"), msg.get("usage")
        if not mid or mid in seen or not isinstance(usage, dict) or msg.get("model") == "<synthetic>":
            continue
        seen.add(mid)
        out.append((i, str(mid), usage))
    return out


def _total_input(usage: dict) -> int:
    return sum(int(usage.get(k) or 0) for k in _USAGE_FIELDS[:3])


def _loads(rows: list[dict]) -> list[dict]:
    """Every skill load in one session: {row, anchor, group, skill, invoked_by}.

    ``anchor`` is where the load's window starts: the first row of the API response
    that made an agent call (so the order of blocks inside a response does not
    matter), or the skill-body row of a typed load. Loads made by one response
    share a ``group``.
    """
    first_row: dict[str, int] = {}
    out: list[dict] = []
    for i, row in enumerate(rows):
        if row.get("isSidechain"):
            continue
        if row.get("type") == "assistant":
            msg = _message(row)
            mid = str(msg.get("id") or f"row{i}")
            first_row.setdefault(mid, i)
            for block in msg.get("content") or []:
                if not (isinstance(block, dict) and block.get("type") == "tool_use"
                        and block.get("name") == "Skill"):
                    continue
                inp = block.get("input")
                name = inp.get("skill") if isinstance(inp, dict) else None
                if name:
                    out.append({"row": i, "anchor": first_row[mid], "group": f"r:{mid}",
                                "skill": str(name), "invoked_by": "agent"})
        elif row.get("type") == "user" and row.get("isMeta") and not row.get("sourceToolUseID"):
            # The body of an AGENT call names its call in sourceToolUseID; a body
            # without one was loaded by a typed command. Measured 2026-11-24 over
            # the corpus: all 81 agent bodies carry it, and all 111 bodies without
            # it follow a typed <command-name>.
            # Known limit: a typed plugin skill (/vendor:alpha) is named by its body
            # directory (alpha), so it can be counted as an owned skill of the same
            # name; agent calls keep the full "vendor:alpha". None seen in the corpus.
            m = _LOAD_RE.search(_text(row))
            if m:
                out.append({"row": i, "anchor": i, "group": f"t:{i}",
                            "skill": Path(m.group(1)).name, "invoked_by": "user"})
    return out


def session_invocations(rows: list[dict]) -> list[dict]:
    """Every skill load in one session, with the token cost of its window.

    A window runs from its load's anchor to the next human prompt or the next load
    made by a DIFFERENT response, whichever is first. Loads made by one response
    share its window, and its tokens are split evenly between them
    (``shared_with`` says how many others).
    """
    loads = _loads(rows)
    responses = _responses(rows)
    prompts = [i for i, row in enumerate(rows) if _is_human_prompt(row)]
    compactions = [i for i, row in enumerate(rows)
                   if row.get("type") == "system" and row.get("subtype") == "compact_boundary"]
    anchors = sorted({ld["anchor"] for ld in loads})
    by_group: dict[str, list[dict]] = defaultdict(list)
    for ld in loads:
        by_group[ld["group"]].append(ld)

    cost_of: dict[str, dict | None] = {}
    for group, members in by_group.items():
        start = members[0]["anchor"]
        ends = [i for i in prompts if i > start] + [a for a in anchors if a > start]
        end = min(ends) if ends else len(rows)
        # `end` is inclusive: when the next load is an agent call, the response that
        # makes it was produced inside THIS window (it read this skill's context), so
        # it is charged here and is also the next window's baseline (P20 #335 r2).
        window = [(i, u) for i, mid, u in responses if start < i <= end]
        before = [(i, u) for i, mid, u in responses if i <= start]
        if not window:
            cost_of[group] = None
            continue
        n = len(members)
        added = None
        if before:
            b_idx, b_usage = before[-1]
            f_idx, f_usage = window[0]
            compacted = any(b_idx < c < f_idx for c in compactions)
            delta = _total_input(f_usage) - _total_input(b_usage)
            added = None if compacted or delta < 0 else delta / n
        cost_of[group] = {
            "turns": len(window),
            "input_tokens": sum(int(u.get("input_tokens") or 0) for _, u in window) / n,
            "cache_write_tokens": sum(int(u.get("cache_creation_input_tokens") or 0)
                                      for _, u in window) / n,
            "cache_read_tokens": sum(int(u.get("cache_read_input_tokens") or 0)
                                     for _, u in window) / n,
            "output_tokens": sum(int(u.get("output_tokens") or 0) for _, u in window) / n,
            "context_added": added,
            "shared_with": n - 1,
        }
    return [{"skill": ld["skill"], "invoked_by": ld["invoked_by"], "cost": cost_of[ld["group"]]}
            for ld in loads]


def _read_rows(path: Path) -> list[dict] | None:
    try:
        blob = path.read_bytes()
    except OSError:
        return None
    if not any(m.search(blob) for m in _MARKERS):  # cheap reject before parsing
        return []
    rows = []
    for line in blob.splitlines():
        try:
            row = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def scan_records(transcript_root: Path) -> tuple[dict[str, list], dict[str, set], int]:
    """Every skill load across real session transcripts, with its cost.

    Returns ({skill: [invocation records]}, {skill: session file names}, scanned).
    """
    records: dict[str, list] = defaultdict(list)
    sessions: dict[str, set] = defaultdict(set)
    scanned = 0
    if not transcript_root.is_dir():
        return records, sessions, scanned
    for f in transcript_root.rglob("*.jsonl"):
        if not is_session_transcript(f.name):
            continue
        scanned += 1
        rows = _read_rows(f)
        if not rows:
            continue
        for inv in session_invocations(rows):
            records[inv["skill"]].append(inv)
            sessions[inv["skill"]].add(f.name)
    return records, sessions, scanned


def scan(transcript_root: Path) -> tuple[Counter, dict[str, set], int]:
    """Count skill loads across real session transcripts only.

    The contract listing.py relies on: (counts, sessions per skill, scanned).
    """
    records, sessions, scanned = scan_records(transcript_root)
    return Counter({k: len(v) for k, v in records.items()}), sessions, scanned


def _median(values: list[int]) -> float | None:
    if not values:
        return None
    v = sorted(values)
    mid = len(v) // 2
    return float(v[mid]) if len(v) % 2 else (v[mid - 1] + v[mid]) / 2


def cost_summary(invocations: list[dict]) -> dict | None:
    """Per-skill medians over the invocations whose window was measurable."""
    measured = [inv["cost"] for inv in invocations if inv.get("cost")]
    if not measured:
        return None
    ctx = [c["context_added"] for c in measured if c.get("context_added") is not None]
    return {
        "measured_invocations": len(measured),
        "median_turns": _median([c["turns"] for c in measured]),
        "median_input_tokens": _median([c["input_tokens"] for c in measured]),
        "median_cache_write_tokens": _median([c["cache_write_tokens"] for c in measured]),
        "median_cache_read_tokens": _median([c["cache_read_tokens"] for c in measured]),
        "median_output_tokens": _median([c["output_tokens"] for c in measured]),
        "median_context_added": _median(ctx),
    }


def build_report(transcript_root: Path, skills_root: Path) -> dict:
    records, sessions, scanned = scan_records(transcript_root)
    counts = Counter({k: len(v) for k, v in records.items()})
    owned = owned_skills(skills_root)
    ranked, external = [], []
    # Ties broken by name, so the ranking does not depend on the order skills were seen.
    for name, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        by = Counter(inv["invoked_by"] for inv in records[name])
        row = {"skill": name, "invocations": n, "sessions": len(sessions[name]),
               "invoked_by": {"agent": by["agent"], "user": by["user"]},
               "cost": cost_summary(records[name])}
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
    print(f"{'#':>3} {'skill':28} {'inv':>5} {'user':>5} {'sess':>5} "
          f"{'out tok':>8} {'ctx add':>8}  evals  path")
    print("-" * 96)

    def num(v):
        return "     n/a" if v is None else f"{v:>8.0f}"

    for i, r in enumerate(rows[: args.top], 1):
        c = r["cost"] or {}
        print(f"{i:>3} {r['skill']:28} {r['invocations']:>5} {r['invoked_by']['user']:>5}"
              f" {r['sessions']:>5} {num(c.get('median_output_tokens'))}"
              f" {num(c.get('median_context_added'))}"
              f"  {'yes' if r['has_evals'] else ' NO':>5}  {r['path']}")
    print("\nout tok / ctx add: medians per invocation; n/a = no measurable window")
    if rep["external_not_ours"]:
        ext = ", ".join(f"{r['skill']}({r['invocations']})" for r in rep["external_not_ours"][:6])
        print(f"\nused but NOT ours (vendored/plugin — edits get overwritten): {ext}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
