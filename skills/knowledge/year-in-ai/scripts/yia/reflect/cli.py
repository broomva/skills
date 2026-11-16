"""``year_in_ai.py reflect <stage>``: the command-line side of the reflect layer."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Optional, Tuple

from ..ledger import store as L
from . import private_dir, write_json, write_private
from . import digest as D
from . import episodes as EP
from . import lint as LINT
from . import outcomes as OUT
from . import output as O
from . import reduce as R
from . import share as SHARE
from . import traces as TR

STAGES = ("episodes", "check", "join", "reduce", "lint", "share", "status")


def add_parser(sub) -> None:
    p = sub.add_parser("reflect", help="episodes, digests, outcomes and a cited reflection of the year")
    p.add_argument("stage", nargs="?", default="status", choices=STAGES)
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--config", help="config file (default ~/.config/year-in-ai/config.json)")
    p.add_argument("--dir", help="reflect root (default ~/.local/share/year-in-ai/reflect)")
    p.add_argument("--ledger", help="ledger directory, used as classification context")
    p.add_argument("--no-ledger", action="store_true", help="classify from the stores alone")
    p.add_argument("--root", action="append", help="extra store root, KEY=PATH (repeatable)")
    p.add_argument("--no-defaults", action="store_true", help="use only config and --root paths")
    p.add_argument("--batch", type=int, help="check: only this batch's episodes, and require all of them")
    p.add_argument("--complete", action="store_true", help="check: fail when any episode lacks a digest")
    p.add_argument("--kg", help="join: knowledge-graph entity directory")
    p.add_argument("--linear-json", help="join: a Linear export, list of {identifier, state, title}")
    p.add_argument("--no-github", action="store_true", help="join: do not ask gh for merged PRs")
    p.add_argument("--file", help="lint/share: the reflection (default <dir>/<year>/reflection.md)")
    p.add_argument("--out", help="share: where to write the redacted copy")
    p.add_argument("--redact-term", action="append", help="share: extra term to redact")
    p.set_defaults(func=run)


def _window(year: int, offset: float) -> Tuple[float, float]:
    zone = _dt.timezone(_dt.timedelta(hours=offset))
    return (_dt.datetime(year, 1, 1, tzinfo=zone).timestamp(), _dt.datetime(year + 1, 1, 1, tzinfo=zone).timestamp())


def _roots_from_args(args) -> dict:
    out: dict = {}
    for item in args.root or []:
        key, _, value = item.partition("=")
        if not value:
            raise SystemExit(f"--root expects KEY=PATH, got {item!r}")
        out.setdefault(key.strip(), []).append(value.strip())
    return out


def run(args: argparse.Namespace) -> int:
    try:
        config = L.load_config(args.config)
    except L.ConfigError as exc:
        print(f"reflect: {exc}", file=sys.stderr)
        return 2
    outdir = private_dir(args.year, args.dir or config.get("reflect_dir"))
    return {"episodes": episodes, "check": check, "join": join, "reduce": reduce, "lint": lint,
            "share": share, "status": status}[args.stage](args, config, outdir)


def episodes(args, config: dict, outdir: Path) -> int:
    try:
        roots = L.resolve_roots(config, _roots_from_args(args), defaults=not args.no_defaults)
    except ValueError as exc:
        print(f"reflect: {exc}", file=sys.stderr)
        return 2
    offset = float(config.get("utc_offset_hours", -5))
    window = _window(args.year, offset)
    text_only = config.get("text_only_until")
    text_only_until = (_dt.datetime.fromisoformat(text_only).replace(tzinfo=_dt.timezone.utc).timestamp()
                       if text_only else None)
    ledger = None if args.no_ledger else L.Ledger(args.ledger or config.get("ledger"))
    classification, sink, reports = EP.collect(roots, window, ledger, text_only_until,
                                               float(config.get("bridged_utc_offset_hours", -5)))
    in_window = [r for r in classification.human_kept if classification.in_window(r["ts"])]
    wanted = {r["sess"] for r in in_window if r["sess"]}
    metas, meta_reports = TR.session_meta(roots, wanted)
    prefixes = set(config["ticket_prefixes"]) if isinstance(config.get("ticket_prefixes"), list) else None
    eps = EP.build(classification, sink, metas, offset, prefixes)
    pending = D.pending(outdir, eps)
    turns = sum(len(e["prompts"]) for e in eps)
    manifest = {
        "year": args.year, "generated": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "episodes": len(eps), "human_turns_in_window": len(in_window), "turns": turns,
        "turns_without_text": len(in_window) - turns,
        "sessions_without_text": len({r["sess"] for r in in_window}) - len(eps),
        "sampled_traces": sum(1 for e in eps if e.get("trace")),
        "ledger_rows_used": ledger is not None,
        "sources": reports, "trace_sources": meta_reports,
    }
    manifest = O.write(outdir, eps, pending, manifest)
    print(f"reflect episodes: {len(eps):,} episodes, {turns:,} turns with text "
          f"({manifest['turns_without_text']:,} human turns no longer have text on disk), "
          f"{manifest['sampled_traces']} sampled traces, {manifest['batches']} batches to digest "
          f"({len(pending)} episodes) -> {outdir}")
    skipped = [r for r in reports + meta_reports if r.get("skipped")]
    for r in skipped:
        print(f"reflect: WARNING {r['source']}: {r['reason']} — episodes from it may be missing.",
              file=sys.stderr)
    return 4 if skipped else 0


def check(args, config: dict, outdir: Path) -> int:
    eps = O.load_episodes(outdir)
    if not eps:
        print("reflect check: no episodes; run `reflect episodes` first", file=sys.stderr)
        return 2
    only = None
    if args.batch is not None:
        entry = next((b for b in O.batch_index(outdir) if b["batch"] == args.batch), None)
        if entry is None:
            print(f"reflect check: no batch {args.batch}", file=sys.stderr)
            return 2
        only = set(entry["episodes"])
    errors, missing, valid = D.status(outdir, eps, only)
    for eid, problems in sorted(errors.items()):
        for problem in problems:
            print(f"{eid}: {problem}")
    scope = f"batch {args.batch}" if only is not None else "all episodes"
    print(f"reflect check ({scope}): {len(valid)} valid, {len(errors)} invalid, {len(missing)} missing")
    if errors or (missing and (only is not None or args.complete)):
        if missing and only is not None:
            print("missing: " + ", ".join(missing))
        return 1
    return 0


def join(args, config: dict, outdir: Path) -> int:
    eps = O.load_episodes(outdir)
    if not eps:
        print("reflect join: no episodes; run `reflect episodes` first", file=sys.stderr)
        return 2
    sources = {}
    harness = sum(1 for e in eps if e.get("harness_prs"))
    sources["harness"] = {"available": harness > 0, "count": harness,
                          "reason": None if harness else "no store recorded pull requests for these sessions"}
    if args.no_github:
        sources["github"], prs = {"available": False, "reason": "skipped (--no-github)"}, []
    else:
        sources["github"], prs = OUT.github_prs(args.year)
    if not sources["github"]["available"]:
        sources["git"], prs = OUT.git_prs(OUT.repo_dirs(eps), args.year)
    else:
        sources["git"] = {"available": False, "reason": "not needed: gh listed the merged PRs"}
    sources["linear"], states = OUT.linear_states(args.linear_json or config.get("linear_json"))
    sources["kg"], entities = OUT.kg_entities(args.kg or config.get("kg_entities"))
    result = OUT.join(eps, sources, prs, states, entities)
    result["prs"] = {p["url"]: p for p in prs}
    write_json(outdir / "outcomes.json", result)
    linked = sum(1 for v in result["episodes"].values() if v["merged_prs"])
    kg = sum(1 for v in result["episodes"].values() if v["kg"])
    for name, s in sources.items():
        state = "ok    " if s["available"] else "absent"
        print(f"  {state} {name:<8} {s.get('count', '') or ''} {s.get('reason') or ''}".rstrip())
    print(f"reflect join: {linked} of {len(eps)} episodes link to a merged PR, {kg} to a KG entity "
          f"-> {outdir / 'outcomes.json'}")
    return 0


def _outcomes(outdir: Path) -> dict:
    path = outdir / "outcomes.json"
    if not path.is_file():
        return {"sources": {"join": {"available": False, "reason": "reflect join has not run"}}, "episodes": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def reduce(args, config: dict, outdir: Path) -> int:
    eps = O.load_episodes(outdir)
    if not eps:
        print("reflect reduce: no episodes; run `reflect episodes` first", file=sys.stderr)
        return 2
    _errors, missing, valid = D.status(outdir, eps)
    manifest = json.loads((outdir / "manifest.json").read_text(encoding="utf-8"))
    data = R.write(outdir, args.year, eps, valid, _outcomes(outdir), manifest)
    print(f"reflect reduce: {len(valid)} of {len(eps)} episodes digested ({len(missing)} missing); "
          f"wrote data.json, index.md and {len(data['by_month'])} month packets in {outdir}")
    return 0


def _reflection(args, outdir: Path) -> Path:
    return Path(args.file).expanduser() if args.file else outdir / "reflection.md"


def lint(args, config: dict, outdir: Path) -> int:
    path = _reflection(args, outdir)
    data_path = outdir / "data.json"
    if not path.is_file() or not data_path.is_file():
        print(f"reflect lint: need {path} and {data_path} (run `reflect reduce`, then write the reflection)",
              file=sys.stderr)
        return 2
    eps = {e["id"]: e for e in O.load_episodes(outdir)}
    data = json.loads(data_path.read_text(encoding="utf-8"))
    errors, stats = LINT.lint(path.read_text(encoding="utf-8"), eps, data)
    for err in errors:
        print(err)
    summary = (f"{stats['claims']} claims, {stats['cited']} cited, {stats['citations']} citations, "
               f"{stats['quotes']} quotes, {stats['numbers']} numbers checked")
    if errors:
        print(f"reflect lint: FAILED with {len(errors)} errors ({summary})")
        return 1
    print(f"reflect lint: ok ({summary})")
    return 0


def share(args, config: dict, outdir: Path) -> int:
    path = _reflection(args, outdir)
    if not path.is_file():
        print(f"reflect share: {path} does not exist", file=sys.stderr)
        return 2
    if not (outdir / "episodes.jsonl").is_file():
        print("reflect share: needs episodes.jsonl to remove text copied from prompts and replies; "
              "run `reflect episodes` first", file=sys.stderr)
        return 2
    texts = [t["text"] for e in O.load_episodes(outdir) for t in e["prompts"] + e["replies"]]
    out = Path(args.out).expanduser() if args.out else outdir / "reflection.share.md"
    draft = SHARE.redact(path.read_text(encoding="utf-8"), args.redact_term or [], texts)
    write_private(out, draft)
    removed = {"quoted or copied spans": draft.count(SHARE.QUOTE_REMOVED), "links": draft.count("«link»"),
               "paths": draft.count("«path»"), "redact terms": draft.count(SHARE.PLACEHOLDER)}
    print(f"reflect share: wrote a REVIEW DRAFT to {out}; removed "
          + ", ".join(f"{n} {kind}" for kind, n in removed.items()))
    print("reflect share: this is not share-safe by itself. Short names, credentials and paraphrased "
          "private details are not detected; read every line, add --redact-term for anything private, "
          "and rerun before it leaves this machine")
    return 0


def status(args, config: dict, outdir: Path) -> int:
    eps = O.load_episodes(outdir)
    if not eps:
        print(f"reflect: nothing yet in {outdir}. Next: reflect episodes --year {args.year}")
        return 0
    errors, missing, valid = D.status(outdir, eps)
    print(f"reflect {args.year} in {outdir}")
    print(f"  episodes  {len(eps):,}; digests {len(valid):,} valid, {len(errors)} invalid, {len(missing)} missing")
    for name in ("outcomes.json", "data.json", "reflection.md"):
        print(f"  {name:<14} {'present' if (outdir / name).is_file() else 'absent'}")
    step: Optional[str] = None
    if missing or errors:
        step = "digest the batches in batches/ (one subagent per batch), then reflect check"
    elif not (outdir / "outcomes.json").is_file():
        step = "reflect join"
    elif not (outdir / "data.json").is_file():
        step = "reflect reduce"
    elif not (outdir / "reflection.md").is_file():
        step = "write reflection.md from months/, index.md and data.json, then reflect lint"
    else:
        step = "reflect lint"
    print(f"  next: {step}")
    return 0
