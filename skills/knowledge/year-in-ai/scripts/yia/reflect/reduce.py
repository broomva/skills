"""The reduce inputs: the data payload every number must come from, and compact month packets.

``data.json`` is the only place a number in ``reflection.md`` may come from;
``reflect lint`` checks every figure against it. ``months/<YYYY-MM>.md`` holds
one compact line block per episode (its digest and joined outcomes), small
enough for one agent to read a month at a time. ``index.md`` lists recurring
topics, ideas, obstacles and quote candidates with the episodes behind them.
"""

from __future__ import annotations

import collections
import re
from pathlib import Path
from typing import Dict, List

from . import write_json, write_private


#: Links that tie a PR to the session itself; a shared ticket only says they are related.
STRONG_VIA = {"mention", "harness", "branch"}


def strong_prs(out: dict) -> List[dict]:
    return [p for p in out.get("merged_prs", []) if STRONG_VIA & set(p["via"])]


def _median(values: List[int]) -> float:
    if not values:
        return 0
    ordered, mid = sorted(values), len(values) // 2
    if len(values) % 2:
        return ordered[mid]
    middle = (ordered[mid - 1] + ordered[mid]) / 2
    return int(middle) if middle == int(middle) else middle


def _pct(part: int, whole: int) -> int:
    return round(100 * part / whole) if whole else 0


def _counted(counter: collections.Counter, whole: int, top: int = 0) -> List[dict]:
    items = counter.most_common(top or None)
    return [{"name": k, "count": v, "pct": _pct(v, whole)} for k, v in items]


def payload(year: int, episodes: List[dict], digests: Dict[str, dict], outcomes: dict, manifest: dict) -> dict:
    """Every number the reflection may cite, computed from episodes, digests and outcomes."""
    joined = outcomes.get("episodes", {})
    n = len(episodes)
    months: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    kinds, steering, status = collections.Counter(), collections.Counter(), collections.Counter()
    topics, skills, commands, repos, harness = (collections.Counter() for _ in range(5))
    month_kinds: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    month_topics: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    merged_urls, tickets_all, kg_all = set(), set(), set()
    corrected = interrupted = with_pr = with_kg = ticket_only = 0
    for e in episodes:
        m = months[e["month"]]
        m["episodes"] += 1
        m["prompts"] += len(e["prompts"])
        m["words"] += e["words"]
        m["corrections"] += len(e["corrections"])
        m["interrupts"] += e["interrupts"]
        m["tool_calls"] += e["tools"]
        harness[e["harness"]] += 1
        if e.get("repo"):
            repos[e["repo"]] += 1
        skills.update({k: 1 for k in e["skills"]})
        commands.update({k: 1 for k in e["commands"]})
        corrected += bool(e["corrections"])
        interrupted += bool(e["interrupts"])
        out = joined.get(e["id"], {})
        strong = strong_prs(out)
        if strong:
            with_pr += 1
            m["episodes_with_merged_pr"] += 1
            merged_urls |= {p["url"] for p in strong}
        elif any("ticket" in p["via"] for p in out.get("merged_prs", [])):
            # Only a shared ticket counts here; a same-named branch in another
            # repository is no evidence at all.
            ticket_only += 1
            m["episodes_with_ticket_linked_pr"] += 1
        if out.get("kg"):
            with_kg += 1
            kg_all |= {k["slug"] for k in out["kg"]}
        tickets_all |= set(e["tickets"])
        d = digests.get(e["id"])
        if d:
            m["digested"] += 1
            kinds[d["kind"]] += 1
            steering[d["steering"]] += 1
            status[d["outcome"]["status"]] += 1
            month_kinds[e["month"]][d["kind"]] += 1
            for t in d["topics"]:
                topics[t.lower()] += 1
                month_topics[e["month"]][t.lower()] += 1
            m[f"outcome_{d['outcome']['status']}"] += 1
    digested = sum(1 for e in episodes if e["id"] in digests)
    by_month = {}
    for month in sorted(months):
        m = months[month]
        by_month[month] = dict(m, correction_rate_pct=_pct(sum(1 for e in episodes if e["month"] == month
                                                                and e["corrections"]), m["episodes"]),
                               kinds=_counted(month_kinds[month], m["digested"], 6),
                               top_topics=_counted(month_topics[month], m["digested"], 8))
    prompts = sum(len(e["prompts"]) for e in episodes)
    return {
        "year": year,
        "totals": {
            "episodes": n, "episodes_digested": digested, "digest_coverage_pct": _pct(digested, n),
            "prompts": prompts, "authored_words": sum(e["words"] for e in episodes),
            "replies": sum(len(e["replies"]) for e in episodes),
            "reply_words": sum(e["reply_words"] for e in episodes),
            "prompts_without_text": sum(e["prompts_without_text"] for e in episodes),
            "corrections": sum(len(e["corrections"]) for e in episodes),
            "episodes_with_corrections": corrected, "episodes_with_corrections_pct": _pct(corrected, n),
            "episodes_with_interrupts": interrupted, "interrupts": sum(e["interrupts"] for e in episodes),
            "tool_calls": sum(e["tools"] for e in episodes), "tool_errors": sum(e["tool_errors"] for e in episodes),
            "subagents": sum(e["subagents"] for e in episodes),
            "active_months": len(months), "active_days": len({d for e in episodes for d in e["days"]}),
            "median_prompts_per_episode": _median([len(e["prompts"]) for e in episodes]),
        },
        "outcomes": {
            "episodes_with_merged_pr": with_pr, "episodes_with_merged_pr_pct": _pct(with_pr, n),
            "merged_prs_linked": len(merged_urls), "tickets_mentioned": len(tickets_all),
            "episodes_with_only_ticket_linked_pr": ticket_only,
            "episodes_with_kg_entity": with_kg, "kg_entities_linked": len(kg_all),
            "sources": outcomes.get("sources", {}),
        },
        "by_month": by_month,
        "by_harness": _counted(harness, n),
        "kinds": _counted(kinds, digested),
        "steering": _counted(steering, digested),
        "outcome_status": _counted(status, digested),
        "topics": _counted(topics, digested, 60),
        "skills": _counted(skills, n, 40),
        "commands": _counted(commands, n, 40),
        "repos": _counted(repos, n, 30),
        "sampled_traces": sum(1 for e in episodes if e.get("trace")),
        "episode_stage": {k: manifest.get(k) for k in ("turns", "turns_without_text", "sessions_without_text",
                                                         "human_turns_in_window", "batches")},
    }


def _line(e: dict, d: dict, out: dict) -> str:
    strong = strong_prs(out)
    prs = ", ".join(p["url"].replace("https://github.com/", "") for p in strong[:8]) or "none"
    if len(strong) > 8:
        prs += f" (+{len(strong) - 8} more)"
    # Only a shared ticket makes a PR "related"; a same-named branch elsewhere is nothing.
    related = sum(1 for p in out.get("merged_prs", []) if p not in strong and "ticket" in p["via"])
    if related:
        prs += f"; {related} more merged PRs share a ticket"
    kg = ", ".join(k["slug"] for k in out.get("kg", [])) or "none"
    where = " ".join(x for x in (e.get("repo") or "", f"@{e['branch']}" if e.get("branch") else "") if x)
    head = (f"### [{e['id']}] {e['first'][:10]} {e['harness']} {where} "
            f"({len(e['prompts'])} prompts, {len(e['corrections'])} corrections, {e['interrupts']} interrupts)")
    if not d:
        return head + "\n- not digested\n"
    lines = [head,
             f"- goal: {d['goal']}",
             f"- kind: {d['kind']}; steering: {d['steering']} — {d['steering_note']}",
             f"- topics: {', '.join(d['topics'])}"]
    if d.get("obstacle"):
        lines.append(f"- obstacle: {d['obstacle']} → {d.get('resolution') or 'unresolved'}")
    lines.append(f"- outcome: {d['outcome']['status']} ({d['outcome']['evidence']}); merged PRs: {prs}; "
                 f"tickets: {', '.join(e['tickets'][:8]) or 'none'}; kg: {kg}")
    if d.get("ideas"):
        lines.append(f"- ideas: {' | '.join(d['ideas'])}")
    if d.get("quote"):
        lines.append(f"- quote: “{d['quote']}”")
    if e.get("skills") or e.get("commands"):
        lines.append(f"- invoked: {', '.join(list(e['skills'])[:6] + list(e['commands'])[:6])}")
    return "\n".join(lines) + "\n"


def write(outdir: Path, year: int, episodes: List[dict], digests: Dict[str, dict], outcomes: dict,
          manifest: dict) -> dict:
    data = payload(year, episodes, digests, outcomes, manifest)
    write_json(outdir / "data.json", data)
    joined = outcomes.get("episodes", {})
    by_month: Dict[str, List[dict]] = collections.defaultdict(list)
    for e in episodes:
        by_month[e["month"]].append(e)
    # A packet from an earlier run for a month no longer in the episode set
    # would feed the monthly readers episodes absent from data.json.
    months_dir = outdir / "months"
    if months_dir.is_dir():
        for stale in months_dir.glob("*.md"):
            # Only packets this step generates (YYYY-MM.md); anything else is left alone.
            if re.fullmatch(r"\d{4}-\d{2}", stale.stem) and stale.stem not in by_month:
                stale.unlink()
    for month, group in sorted(by_month.items()):
        stats = data["by_month"][month]
        body = [f"# {month}: {stats['episodes']} episodes, {stats['prompts']} prompts, "
                f"{stats.get('episodes_with_merged_pr', 0)} with a merged PR\n"]
        body += [_line(e, digests.get(e["id"]), joined.get(e["id"], {})) for e in group]
        write_private(outdir / "months" / f"{month}.md", "\n".join(body))
    # The cross-month index: recurring topics, ideas, obstacles and quotes, with their episodes.
    topic_eps: Dict[str, List[str]] = collections.defaultdict(list)
    ideas, obstacles, quotes = [], [], []
    for e in episodes:
        d = digests.get(e["id"])
        if not d:
            continue
        for t in d["topics"]:
            topic_eps[t.lower()].append(e["id"])
        ideas += [(e["first"][:10], i, e["id"]) for i in d["ideas"]]
        if d.get("obstacle"):
            obstacles.append((e["score"]["corrections"], e["first"][:10], d["obstacle"], d.get("resolution"), e["id"]))
        if d.get("quote"):
            quotes.append((e["first"][:10], d["quote"], e["id"]))
    lines = ["# Index\n", "## Recurring topics (3+ episodes)\n"]
    for topic, ids in sorted(topic_eps.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        if len(ids) >= 3:
            lines.append(f"- {topic} ({len(ids)}): {', '.join(ids[:40])}")
    lines.append("\n## Obstacles, most-corrected sessions first\n")
    for corr, day, obstacle, resolution, eid in sorted(obstacles, key=lambda x: (-x[0], x[1]))[:250]:
        lines.append(f"- [{eid}] {day} ({corr} corrections) {obstacle} → {resolution or 'unresolved'}")
    lines.append("\n## Ideas, in time order\n")
    lines += [f"- [{eid}] {day} {idea}" for day, idea, eid in sorted(ideas)]
    lines.append("\n## Quote candidates (verbatim user words)\n")
    lines += [f"- [{eid}] {day} “{q}”" for day, q, eid in sorted(quotes)]
    write_private(outdir / "index.md", "\n".join(lines) + "\n")
    return data
