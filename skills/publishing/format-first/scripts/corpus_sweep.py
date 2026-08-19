#!/usr/bin/env python3
"""corpus_sweep — run format_lint over a tree and report what fires, per rule.

Two uses, both real:

  1. Before adopting the gate, point it at your existing library and see what it would
     say. A rule that fires on a third of your archive is a rule you will learn to ignore.
  2. When a ledger pattern is widened, sweep the SAME tree with the old and new ledger and
     read the delta. Every added finding must be a true positive, or the widening bought
     coverage with noise. `--compare <old-ledger.json>` prints exactly that diff.

Usage:
    corpus_sweep.py <dir>... [--ext .md] [--compare OLD_LEDGER] [--json]
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import format_lint as fl  # noqa: E402


def walk(roots: list[str], ext: str) -> list[Path]:
    out: list[Path] = []
    for r in roots:
        p = Path(r)
        out.extend(sorted(p.rglob(f"*{ext}")) if p.is_dir() else [p])
    return [f for f in out if f.is_file()]


def scan(files: list[Path], ledger: dict) -> tuple[set, int]:
    """Return (findings as hashable keys, crash count). A crash is a defect, not a finding."""
    keys, crashes = set(), 0
    for f in files:
        try:
            found = fl.lint_text(f.read_text(encoding="utf-8", errors="replace"), ledger)
        except fl.LedgerError:
            # A malformed ledger is not "this file crashed". Swallowing it here is exactly
            # how a broken comparison ledger reported every current finding as new coverage.
            raise
        except Exception:
            crashes += 1
            continue
        for x in found:
            keys.add((str(f), x["line"], x["id"], x["matched"]))
    return keys, crashes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="corpus_sweep")
    ap.add_argument("roots", nargs="+")
    ap.add_argument("--ext", default=".md")
    ap.add_argument("--compare", type=Path, help="a second ledger; print the added/removed delta")
    ap.add_argument("--ledger", type=Path, default=fl.LEDGER)
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)

    files = walk(args.roots, args.ext)
    if not files:
        print(f"corpus_sweep: no *{args.ext} under {args.roots}", file=sys.stderr)
        return 2

    try:
        new, crashes = scan(files, fl.load_ledger(args.ledger))
    except fl.LedgerError as exc:
        print(exc, file=sys.stderr)
        return 2
    by_rule = collections.Counter(k[2] for k in new)
    report: dict = {
        "files": len(files),
        "crashes": crashes,
        "findings": len(new),
        "by_rule": dict(by_rule.most_common()),
    }

    if args.compare:
        try:
            old, old_crashes = scan(files, fl.load_ledger(args.compare))
        except fl.LedgerError as exc:
            print(f"corpus_sweep: comparison ledger unusable — {exc}", file=sys.stderr)
            return 2
        # NEVER discard this. If the old ledger crashes on every file its finding set is
        # empty, so every current finding reads as newly ADDED and a widening that bought
        # nothing certifies itself as pure gain.
        report["old_crashes"] = old_crashes
        report["added"] = [
            {"file": k[0], "line": k[1], "id": k[2], "matched": k[3]} for k in sorted(new - old)
        ]
        report["removed"] = [
            {"file": k[0], "line": k[1], "id": k[2], "matched": k[3]} for k in sorted(old - new)
        ]

    failed = report["crashes"] or report.get("old_crashes", 0)

    if args.as_json:
        print(json.dumps(report, indent=2))
        return 1 if failed else 0

    print(
        f"files={report['files']}  crashes={report['crashes']}  findings={report['findings']}"
        + (f"  old_crashes={report['old_crashes']}" if "old_crashes" in report else "")
    )
    for rid, n in report["by_rule"].items():
        print(f"  {n:>6}  {rid}")
    for label in ("added", "removed"):
        rows = report.get(label)
        if rows is None:
            continue
        print(f"\n{label.upper()} vs {args.compare} ({len(rows)}):")
        for r in rows:
            print(f"  {Path(r['file']).name}:{r['line']}  [{r['id']}]  «{r['matched'][:70]}»")
    if failed:
        print(
            f"corpus_sweep: {report['crashes']} crash(es) on the current ledger and "
            f"{report.get('old_crashes', 0)} on the comparison ledger — the delta above is "
            "NOT trustworthy.",
            file=sys.stderr,
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
