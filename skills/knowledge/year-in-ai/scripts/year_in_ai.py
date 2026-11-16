#!/usr/bin/env python3
"""year-in-ai — a Wrapped-style retrospective over your local AI history.

    year_in_ai.py extract --year 2026 --out wrapped.json
    year_in_ai.py render  --payload wrapped.json --out deck.html
    year_in_ai.py run     --year 2026 --outdir ./out --share
    year_in_ai.py reflect episodes --year 2026   (then check, join, reduce, lint)

``extract`` is pure and deterministic: it reads local files and writes JSON.
``render`` never reads the corpus — only the payload — so the deck can be
rebuilt, restyled, or re-rendered offline without touching the transcripts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from yia import __version__  # noqa: E402
from yia.build import build_payload, window_for_year  # noqa: E402
from yia.discovery import discover  # noqa: E402
from yia.redact import redact  # noqa: E402


def _add_window_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--year", type=int, help="calendar year to cover, e.g. 2026")
    parser.add_argument("--since", help="ISO date lower bound (inclusive)")
    parser.add_argument("--until", help="ISO date upper bound (exclusive)")


def _add_source_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workspace",
        default=None,
        help="root to scan for bridged sessions, entities and repos (default: cwd)",
    )
    parser.add_argument("--claude-projects", help="override the Claude transcript root")
    parser.add_argument("--claude-history", help="override the prompt-history file")
    parser.add_argument("--codex-sessions", help="override the Codex sessions root")
    parser.add_argument("--kg-entities", help="override the entity-graph root")
    parser.add_argument("--memory-dir", help="override the agent memory directory")
    parser.add_argument("--bridged-roots", help="override the bridged-session directory")
    parser.add_argument("--git-roots", help="override the git repository root")
    parser.add_argument("--git-author", help="restrict commit counts to this author")
    parser.add_argument(
        "--no-outcomes",
        action="store_true",
        help="skip the knowledge-graph, memory and git readers",
    )
    parser.add_argument(
        "--no-scan",
        action="store_true",
        help="do not walk the workspace looking for bridged sessions or repos",
    )


def _overrides(args: argparse.Namespace) -> dict[str, str]:
    mapping = {
        "claude_projects": args.claude_projects,
        "claude_history": args.claude_history,
        "codex_sessions": args.codex_sessions,
        "kg_entities": args.kg_entities,
        "memory_dir": args.memory_dir,
        "bridged_roots": args.bridged_roots,
        "git_roots": args.git_roots,
    }
    return {k: v for k, v in mapping.items() if v}


def do_extract(args: argparse.Namespace) -> dict:
    window = window_for_year(args.year, args.since, args.until)
    stores = discover(
        workspace=args.workspace,
        overrides=_overrides(args),
        scan_workspace=not args.no_scan,
    )
    if args.verbose:
        print("stores:", json.dumps(stores.describe(), indent=2), file=sys.stderr)
    started = time.time()
    payload = build_payload(
        stores,
        window,
        git_author=args.git_author,
        include_outcomes=not args.no_outcomes,
    )
    payload["extraction_seconds"] = round(time.time() - started, 2)
    if getattr(args, "share", False):
        payload = redact(payload, extra_terms=getattr(args, "redact_term", None) or [])
    return payload


def _write(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def cmd_extract(args: argparse.Namespace) -> int:
    payload = do_extract(args)
    out = Path(args.out)
    _write(payload, out)
    totals = payload["totals"]
    window = payload["window"]
    print(
        f"wrote {out} — {totals['events']:,} events, {totals['sessions']:,} sessions, "
        f"{window['observed_first']} → {window['observed_last']} "
        f"({payload['extraction_seconds']}s)"
    )
    if not payload["honesty"]["covers_full_year"]:
        days = payload["honesty"]["observed_days"]
        print(f"note: corpus spans {days} days, not a full year — the deck will say so.")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    from yia.render import render_deck

    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    html = render_deck(payload)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html):,} bytes, self-contained)")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from yia.render import render_deck

    outdir = Path(args.outdir)
    payload = do_extract(args)
    _write(payload, outdir / "wrapped.json")
    html = render_deck(payload)
    (outdir / "deck.html").write_text(html, encoding="utf-8")
    print(f"wrote {outdir / 'wrapped.json'} and {outdir / 'deck.html'}")
    return 0


def _roots_from_args(args: argparse.Namespace) -> dict:
    """Pairs like ``claude_projects=/path`` from repeated --root flags."""
    out: dict = {}
    for item in args.root or []:
        key, _, value = item.partition("=")
        if not value:
            raise SystemExit(f"--root expects KEY=PATH, got {item!r}")
        out.setdefault(key.strip(), []).append(value.strip())
    return out


def _since(args: argparse.Namespace):
    from datetime import datetime, timezone

    if getattr(args, "backfill", False):
        return None
    if args.since:
        return datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc).timestamp()
    return time.time() - args.days * 86400


def cmd_harvest(args: argparse.Namespace) -> int:
    from yia.ledger import archive as A
    from yia.ledger import store as L

    try:
        config = L.load_config(args.config)
        roots = L.resolve_roots(config, _roots_from_args(args), defaults=not args.no_defaults)
    except ValueError as exc:
        print(f"harvest: {exc}", file=sys.stderr)
        return 2
    ledger = L.Ledger(args.ledger or config.get("ledger"))
    try:
        entry = L.harvest(ledger, roots, _since(args), float(config.get("bridged_utc_offset_hours", -5)))
    except L.LegacyLedgerError as exc:
        print(f"harvest: refused — {exc}", file=sys.stderr)
        return 3
    added = sum(entry["added"].values())
    print(f"harvest: {added:,} new rows into {ledger.dir} in {entry['seconds']}s")
    for src in entry["sources"]:
        state = "ok " if src["available"] else "-- "
        span = f"{(src['first'] or '')[:10]} → {(src['last'] or '')[:10]}" if src["records"] else (src["reason"] or "empty")
        print(f"  {state}{src['source']:<15} {src['records']:>8,} records  {span}")
    skipped = [src for src in entry["sources"] if src.get("skipped")]
    for src in skipped:
        hint = " Install zstd (brew install zstd) and run harvest again." if "zstd" in (src["reason"] or "") else ""
        print(f"harvest: WARNING {src['source']}: {src['reason']} — totals are incomplete.{hint}",
              file=sys.stderr)
    archive_to = args.archive_to or config.get("archive_to")
    if archive_to:
        try:
            result = A.archive(Path(os.path.expanduser(archive_to)), ledger.dir)
        except (FileNotFoundError, ValueError) as exc:
            print(f"archive: skipped — {exc}", file=sys.stderr)
            return 2
        for sub, counts in result.items():
            print(f"archive: {sub}: {counts['copied']} copied, {counts['revisions']} kept as revisions "
                  f"({counts['bytes'] / 1e6:.0f} MB), {counts['unchanged']} unchanged, {counts['errors']} errors")
    return 4 if skipped else 0


def cmd_attention(args: argparse.Namespace) -> int:
    from datetime import datetime, timezone

    from yia.ledger import attention as T
    from yia.ledger import store as L

    try:
        config = L.load_config(args.config)
    except L.ConfigError as exc:
        print(f"attention: {exc}", file=sys.stderr)
        return 2
    ledger = L.Ledger(args.ledger or config.get("ledger"))
    since = until = None
    offset = float(config.get("utc_offset_hours", -5))
    if args.year:
        # The year is the operator's local calendar year, the same zone the fold reports in.
        from datetime import timedelta

        zone = timezone(timedelta(hours=offset))
        since = datetime(args.year, 1, 1, tzinfo=zone).timestamp()
        until = datetime(args.year + 1, 1, 1, tzinfo=zone).timestamp()
    text_only_until = config.get("text_only_until")
    # Read the whole ledger as context, so every prompt keeps its replies and
    # every reply its final revision wherever they fall; only the window is
    # reported. A year of heavy use is ~80k rows, so this is cheap.
    rows = list(ledger.rows())
    if ledger.legacy_rows:
        print(f"note: ignored {ledger.legacy_rows:,} rows of an older ledger schema; "
              "rebuild with `harvest --backfill` into a fresh ledger directory", file=sys.stderr)
    summary = T.fold(
        rows,
        window=(since, until),
        read_share=(args.read_low, (args.read_low + args.read_high) / 2, args.read_high),
        utc_offset_hours=offset,
        text_only_until=datetime.fromisoformat(text_only_until).replace(tzinfo=timezone.utc).timestamp()
        if text_only_until else None,
    )
    text = json.dumps(summary, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="year-in-ai", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"year-in-ai {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_extract = sub.add_parser("extract", help="scan local history and write wrapped.json")
    _add_window_args(p_extract)
    _add_source_args(p_extract)
    p_extract.add_argument("--out", default="wrapped.json")
    p_extract.add_argument("--share", action="store_true", help="apply share-safe redaction")
    p_extract.add_argument("--redact-term", action="append", help="extra term to redact")
    p_extract.set_defaults(func=cmd_extract)

    p_render = sub.add_parser("render", help="render a deck from an existing payload")
    p_render.add_argument("--payload", default="wrapped.json")
    p_render.add_argument("--out", default="deck.html")
    p_render.set_defaults(func=cmd_render)

    p_run = sub.add_parser("run", help="extract and render in one step")
    _add_window_args(p_run)
    _add_source_args(p_run)
    p_run.add_argument("--outdir", default="./year-in-ai-out")
    p_run.add_argument("--share", action="store_true")
    p_run.add_argument("--redact-term", action="append")
    p_run.set_defaults(func=cmd_run)

    p_harvest = sub.add_parser("harvest", help="fold recent turns into the text-free ledger")
    p_harvest.add_argument("--ledger", help="ledger directory (default ~/.local/share/year-in-ai/ledger)")
    p_harvest.add_argument("--config", help="config file (default ~/.config/year-in-ai/config.json)")
    p_harvest.add_argument("--days", type=int, default=45, help="look back this many days (default 45)")
    p_harvest.add_argument("--since", help="ISO date lower bound instead of --days")
    p_harvest.add_argument("--backfill", action="store_true", help="read everything still on disk")
    p_harvest.add_argument("--root", action="append", help="extra store root, KEY=PATH (repeatable)")
    p_harvest.add_argument("--no-defaults", action="store_true", help="use only config and --root paths")
    p_harvest.add_argument("--archive-to", help="also copy pruning stores into this archive root")
    p_harvest.set_defaults(func=cmd_harvest)

    p_attention = sub.add_parser("attention", help="words written and read, from the ledger")
    p_attention.add_argument("--ledger")
    p_attention.add_argument("--config")
    p_attention.add_argument("--year", type=int)
    p_attention.add_argument("--read-low", type=float, default=0.60)
    p_attention.add_argument("--read-high", type=float, default=0.70)
    p_attention.add_argument("--out")
    p_attention.set_defaults(func=cmd_attention)

    from yia.reflect import cli as reflect_cli

    reflect_cli.add_parser(sub)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
