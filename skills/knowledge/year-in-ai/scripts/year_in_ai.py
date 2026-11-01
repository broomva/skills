#!/usr/bin/env python3
"""year-in-ai — a Wrapped-style retrospective over your local AI history.

    year_in_ai.py extract --year 2026 --out wrapped.json
    year_in_ai.py render  --payload wrapped.json --out deck.html
    year_in_ai.py run     --year 2026 --outdir ./out --share

``extract`` is pure and deterministic: it reads local files and writes JSON.
``render`` never reads the corpus — only the payload — so the deck can be
rebuilt, restyled, or re-rendered offline without touching the transcripts.
"""

from __future__ import annotations

import argparse
import json
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

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
