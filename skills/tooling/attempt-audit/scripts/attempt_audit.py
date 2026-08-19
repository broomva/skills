#!/usr/bin/env python3
"""attempt-audit — find absence-assertions that carry no attempt-record.

An absence with no attempt-record is not evidence. This finds the concrete,
machine-detectable form of that: a function that returns an empty sentinel when
a guard was SKIPPED, using the same value it returns when the work RAN and found
nothing. The caller cannot tell those apart.

The reference case (scripts/video_ingest.py in broomva/workspace):

    def load_transcript(info, allow_whisper, outdir):
        ...
        if allow_whisper:                        # <- guard on a parameter
            cues = _whisper_faster(...) or ...
            if cues:
                return join_deoverlap(...), cues # <- computed result
        return "", []                            # <- same value when SKIPPED

A caller receiving ("", []) cannot distinguish "ASR ran, clip was silent" from
"ASR was never invoked". Downstream, that became a confident `frames-mandatory`
verdict with an empty degradations list on a clip carrying 282 words.

WHAT THIS DOES NOT DO: it does not find every absence-without-attempt-record.
It finds one syntactic shape. A clean run means "this shape was not found in the
files I could parse", never "your absences are all evidenced". The summary says
so, and says which files it could not read -- because a tool that reports
"nothing found" identically whether it scanned 400 files or 0 would be the very
defect it audits.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "build", "dist",
    ".worktrees", ".next", ".cache", "site-packages", ".eggs",
}

# Names that, when appended to / called on the skipped path, mean the skip WAS
# recorded -- so the function is honest and must not be flagged.
RECORD_HINTS = (
    "degradation", "warning", "warn", "skip", "unattempted", "note", "notes",
    "diagnostic", "reason", "error", "err", "log", "logger", "attempted",
    "audit", "trace", "record",
)


def _is_empty_sentinel(node: ast.AST | None) -> bool:
    """True for None / [] / {} / '' / 0 / False / set() / tuples of those."""
    if node is None:
        return True
    if isinstance(node, ast.Constant):
        # NOT 0 / False. `return 0` from a cmd_* handler is process SUCCESS, and
        # `False` is a legitimate answer, not an absence. Including them made
        # every `def cmd_x(args) -> int` a candidate. Precision over recall: this
        # is a tripwire, and a noisy tripwire gets muted.
        return node.value is None or node.value == "" or node.value == b""
    if isinstance(node, (ast.List, ast.Dict, ast.Set)):
        return not (getattr(node, "elts", None) or getattr(node, "keys", None))
    if isinstance(node, ast.Tuple):
        return bool(node.elts) and all(_is_empty_sentinel(e) for e in node.elts)
    if isinstance(node, ast.Call):
        f = node.func
        return isinstance(f, ast.Name) and f.id in {"list", "dict", "set", "tuple"} and not node.args
    return False


def _records_a_skip(nodes: list[ast.AST]) -> bool:
    """Does this code record that something was skipped? Then it is honest."""
    for n in nodes:
        for sub in ast.walk(n):
            if isinstance(sub, ast.Raise):
                return True
            name = ""
            if isinstance(sub, ast.Call):
                f = sub.func
                if isinstance(f, ast.Attribute):
                    name = f"{getattr(f.value, 'id', '')}.{f.attr}"
                elif isinstance(f, ast.Name):
                    name = f.id
            elif isinstance(sub, ast.Name):
                name = sub.id
            if any(h in name.lower() for h in RECORD_HINTS):
                return True
    return False


def _switch_name(test: ast.AST) -> str | None:
    """The parameter this guard switches on -- or None if it is not a switch.

    ONLY a bare truthiness test counts: `if flag:` or `if not flag:`. A compound
    test (`if a is not None and sha256(f) == expected`) is a computation over
    data, and naming one of its operands produces a false sentence: the tool
    used to print "Returns None when `expected_hash` is false" for a guard that
    never tests `expected_hash`'s truthiness. A tool built to stop bogus
    confident verdicts must not emit them.
    """
    if isinstance(test, ast.Name):
        return test.id
    if (isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not)
            and isinstance(test.operand, ast.Name)):
        return test.operand.id
    return None


class _FnVisitor(ast.NodeVisitor):
    def __init__(self, path: str, src: str):
        self.path, self.src = path, src
        self.findings: list[dict] = []

    def visit_FunctionDef(self, node):  # noqa: N802
        self._check(node)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef  # noqa: N815

    def _check(self, fn):
        params = {a.arg for a in
                  list(fn.args.posonlyargs) + list(fn.args.args) + list(fn.args.kwonlyargs)}
        if fn.args.vararg:
            params.add(fn.args.vararg.arg)
        if fn.args.kwarg:
            params.add(fn.args.kwarg.arg)

        # The fall-through: a `return <empty sentinel>` at the function's top level.
        tail = [s for s in fn.body if isinstance(s, ast.Return) and _is_empty_sentinel(s.value)]
        if not tail:
            return
        fallthrough = tail[-1]

        # A top-level `if` GATING WORK, whose test reads a PARAMETER (a
        # caller-supplied switch), containing a return of a COMPUTED value.
        #
        # "Gating work" is load-bearing. A guard whose body immediately returns a
        # constant is a VALIDATION branch -- every guard runs, nothing is
        # skipped, and the fall-through legitimately means "all checks passed".
        # Without this the detector flags `ingest_failure_reason`-shaped
        # functions, which are honest. Requiring a Call or Assign inside the
        # guard restricts it to branches where work was actually skipped.
        candidates = []
        for stmt in fn.body:
            if not isinstance(stmt, ast.If) or stmt.lineno > fallthrough.lineno:
                continue
            sw = _switch_name(stmt.test)
            gnames = {sw} & params if sw else set()
            if not gnames:
                continue
            computed = [r for r in ast.walk(stmt) if isinstance(r, ast.Return)
                        and not _is_empty_sentinel(r.value)]
            if not computed:
                continue
            # Walk the BODY only. Walking the whole If counts calls inside the
            # TEST as work, so `if len(text) < 5: return True` looked like a
            # skipped-work branch when its body is a bare constant return. A body that
            # immediately returns a constant is a validation branch: every guard
            # ran and nothing was skipped.
            does_work = any(
                isinstance(n, (ast.Call, ast.Assign, ast.AugAssign, ast.AnnAssign,
                               ast.For, ast.While, ast.With))
                for st in stmt.body for n in ast.walk(st)
                if not isinstance(n, ast.Return))
            if not does_work:
                continue
            # The guard must be the LAST thing before the sentinel. If real work
            # sits between them, the function tried an ALTERNATIVE rather than
            # skipping outright -- `_show_or_disk_hashed` skips a git read when
            # `sha` is empty but then reads from disk, so None means "could not
            # recover", not "never attempted".
            body = list(fn.body)
            if body.index(stmt) != body.index(fallthrough) - 1:
                continue
            candidates.append((stmt, gnames))

        for stmt, gnames in candidates:
            # Honest already? A recorded skip on the else-path or before the tail.
            after = [s for s in fn.body if getattr(s, "lineno", 0) > stmt.end_lineno
                     and getattr(s, "lineno", 0) <= fallthrough.lineno]
            if _records_a_skip(list(stmt.orelse) + after):
                continue
            # One finding per function: this is a tripwire, and a second switch
            # in the same function is the same conversation.
            self.findings.append({
                "file": self.path,
                "line": fallthrough.lineno,
                "function": fn.name,
                "guard": next(iter(gnames)),  # _switch_name yields at most one
                "guard_line": stmt.lineno,
                "returns": ast.unparse(fallthrough.value) if fallthrough.value is not None else "None",
            })
            return


def audit_source(src: str, path: str) -> list[dict]:
    v = _FnVisitor(path, src)
    v.visit(ast.parse(src))
    return v.findings


def collect_py(root: Path) -> tuple[list[Path], list[str], list[str]]:
    """Return (files, skipped_dirs, walk_errors).

    Skipped directories are RETURNED, not swallowed. An earlier version filtered
    them inside the generator and reported only the files it read, so most of a
    real tree could go unvisited with nothing in the output saying so. A tool
    whose entire subject is unreported gaps cannot have one.
    """
    if root.is_file():
        return [root], [], []
    files: list[Path] = []
    skipped: list[str] = []
    errors: list[str] = []

    def _onerror(exc: OSError) -> None:
        errors.append(f"{getattr(exc, 'filename', '?')}: {exc.__class__.__name__}: {exc}")

    for dirpath, dirnames, filenames in os.walk(root, onerror=_onerror):
        keep = []
        for d in dirnames:
            if d in SKIP_DIRS or d.startswith("."):
                skipped.append(os.path.relpath(os.path.join(dirpath, d), root))
            else:
                keep.append(d)
        dirnames[:] = keep
        for f in filenames:
            if f.endswith(".py"):
                files.append(Path(dirpath) / f)
    return files, skipped, errors


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="attempt-audit",
        description="Find absence-assertions that carry no attempt-record.")
    ap.add_argument("path", nargs="?", default=".",
                    help="file or directory (default: current directory)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    root = Path(args.path).resolve()
    if not root.exists():
        if args.json:
            print(json.dumps({"scanned": 0, "findings": [], "unreadable": [],
                              "skipped_dirs": [], "walk_errors": [],
                              "error": f"no such path: {root}"}, indent=2))
        print(f"attempt-audit: no such path: {root}", file=sys.stderr)
        return 2

    files, skipped_dirs, walk_errors = collect_py(root)
    findings, unreadable, scanned = [], [], 0
    for p in files:
        try:
            src = p.read_text(encoding="utf-8")
            findings.extend(audit_source(src, str(p)))
            scanned += 1
        except (SyntaxError, ValueError, UnicodeDecodeError, OSError) as exc:
            unreadable.append({"file": str(p), "reason": f"{type(exc).__name__}: {exc}"})

    if args.json:
        print(json.dumps({
            "scanned": scanned,
            "findings": findings,
            "unreadable": unreadable,
            "skipped_dirs": skipped_dirs,
            "walk_errors": walk_errors,
            "coverage_note": ("directories in skipped_dirs were NOT audited; "
                              "a clean result covers only 'scanned' files"),
        }, indent=2))
    else:
        for f in findings:
            rel = os.path.relpath(f["file"], os.getcwd())
            print(f"\n{rel}:{f['line']}  {f['function']}()")
            print(f"  Returns {f['returns']} when `{f['guard']}` is false — the same value it")
            print(f"  returns when the work ran and found nothing. A caller cannot tell")
            print(f"  \"never attempted\" from \"attempted, and empty\".")
            print(f"  Guard at line {f['guard_line']} is skippable and records nothing.")
            print(f"  Fix: return a distinct value, or record the skip in the same object.")

        print()
        if scanned == 0:
            print("Scanned 0 files — nothing was audited. This is NOT a clean result.")
        elif findings:
            print(f"Found {len(findings)} in {scanned} files.")
        else:
            print(f"Scanned {scanned} files. This shape was not found —")
            print("which is not the same as every absence being evidenced.")

        if skipped_dirs:
            shown = ", ".join(sorted(set(skipped_dirs))[:6])
            more = "" if len(set(skipped_dirs)) <= 6 else f", +{len(set(skipped_dirs))-6} more"
            print(f"\nSkipped {len(set(skipped_dirs))} director(ies) — NOT audited: {shown}{more}")
        if walk_errors:
            print(f"\nCould not enter {len(walk_errors)} director(ies) — NOT audited:")
            for e in walk_errors[:5]:
                # Truncate the MESSAGE, never the path: `e[:100]` used to eat the
                # identifying tail on any realistic path, printing a directory
                # prefix where the directory's name should be.
                where, _, why = e.partition(": ")
                print(f"  {where}  ({why[:60]})")
        if unreadable:
            print(f"\nCould not read {len(unreadable)} file(s) — these were NOT audited:")
            for u in unreadable:
                print(f"  {os.path.relpath(u['file'], os.getcwd())}: {u['reason'][:90]}")

    # Exit 0 means "I audited this tree and found nothing". If part of the tree
    # could not be entered or parsed, that sentence is not true, so 0 is not
    # available: an incomplete scan reporting success would be this tool's own
    # defect. Earlier it returned 0 with four unreachable defect files and a
    # PermissionError on the tree, and the CI step consumed only that code.
    if scanned == 0 or walk_errors or unreadable:
        return 2
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
