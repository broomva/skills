#!/usr/bin/env python3
"""Audit a simulation package against its claim ledger.

A simulation that looks right is evidence that it looks right. This script
checks the part that can be decided without looking: that every claim the
package makes is either enforced by something that can fail, or labelled as
unchecked.

The ledger is `sim-claims.yaml` (or `.json`) in the package directory. It lists
the reference files, the claims, the numbers quoted in prose, and one-line code
changes ("mutations") that must turn a test red.

Checks:

  ledger       the ledger parses and its ids resolve
  asserting    every test file contains an assertion (a test that only prints
               passes whatever the physics does)
  claims       each checked claim names a test file that exists and asserts
  references   each reference file states a URL and a fetch date, and something
               under the tests reads it (a table nobody loads was retyped); a
               reference claim with no stored table must cite its source
  coverage     the ledger has a negative control, an anchor computed outside
               the model, and at least one stated limit
  quoted       each quoted number appears in the docs, and (--run-report) in
               the output of the report command
  mutations    each mutation applies exactly once, and (--run-mutations) makes
               its test command fail in a copy of the package

Exit 0 when nothing failed, 1 when a check failed, 2 when the ledger could not
be read. A check that needs a flag that was not given reports SKIP, never PASS.

Stdlib only for a JSON ledger; a YAML ledger needs PyYAML.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

LEDGER_NAMES = ("sim-claims.yaml", "sim-claims.yml", "sim-claims.json")

#: A claim is enforced by a test. Each kind says what the test compares with.
CHECKED_KINDS = {
    "reference": "a published table or value, stored with its source",
    "independent": "the same quantity computed another way",
    "conservation": "a conservation law or an identity of the equations",
    "control": "a null input that must give a null output",
}
#: A claim nothing enforces. It must be labelled so the prose can say so.
UNCHECKED_KINDS = {
    "prediction": "a model result with no measurement to compare",
    "convention": "a choice or typical value, not a measurement",
    "omitted": "physics left out",
}
KINDS = {**CHECKED_KINDS, **UNCHECKED_KINDS}

#: Constructs that can make a test fail. Matched after comments are stripped.
ASSERTION = re.compile(
    r"\bexpect\s*\("
    r"|\bassert\w*\s*[(!]"
    r"|\bassert\s+\S"
    r"|\bEXPECT_[A-Z]+\s*\("
    r"|\bASSERT_[A-Z]+\s*\("
    r"|\bpytest\.(raises|fail|approx)\b"
    r"|\bt\.(Error|Errorf|Fatal|Fatalf|Fail|FailNow)\s*\("
    r"|\b(sys\.exit|process\.exit|os\.Exit|exit)\s*\(\s*[1-9]"
    r"|\bthrow\s+\w"
    r"|\braise\s+\w"
    r"|\bpanic!?\s*\("
    r"|\.should\b"
)
URL = re.compile(r"https?://\S+")
DATE = re.compile(r"\b(19|20)\d{2}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b")
#: How many leading lines of a reference file may carry its provenance.
HEADER_LINES = 40
#: Directories linked into the mutation copy instead of copied.
DEFAULT_LINKS = ("node_modules", ".venv", "venv", "target")
DEFAULT_TIMEOUT = 600

PASS, FAIL, WARN, SKIP = "PASS", "FAIL", "WARN", "SKIP"


class LedgerError(Exception):
    """The ledger is missing, unparseable, or not shaped like a ledger."""


@dataclass
class Result:
    check: str
    status: str
    detail: str
    subject: str = ""

    def as_dict(self) -> dict:
        return {
            "check": self.check,
            "status": self.status,
            "subject": self.subject,
            "detail": self.detail,
        }


@dataclass
class Audit:
    results: list[Result] = field(default_factory=list)

    def add(self, check: str, status: str, detail: str, subject: str = "") -> None:
        self.results.append(Result(check, status, detail, subject))

    def failed(self, strict: bool) -> bool:
        bad = {FAIL, WARN} if strict else {FAIL}
        return any(r.status in bad for r in self.results)


def find_ledger(package: Path) -> Path:
    for name in LEDGER_NAMES:
        candidate = package / name
        if candidate.is_file():
            return candidate
    raise LedgerError(f"no ledger in {package} (looked for {', '.join(LEDGER_NAMES)})")


def load_ledger(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LedgerError(f"{path.name}: {exc}") from exc
    else:
        try:
            import yaml
        except ImportError as exc:
            raise LedgerError(
                f"{path.name} is YAML and PyYAML is not installed "
                "(pip install pyyaml, or write sim-claims.json)"
            ) from exc
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise LedgerError(f"{path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise LedgerError(f"{path.name}: the top level must be a mapping")
    return data


def _strings(value) -> list[str]:
    """A string or a list of strings, as a list. Anything else is empty."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    return []


def _inside(package: Path, relative: str) -> Path | None:
    """`relative` resolved under `package`, or None if it escapes it."""
    target = (package / relative).resolve()
    root = package.resolve()
    if target != root and root not in target.parents:
        return None
    return target


def strip_comments(text: str) -> str:
    """Drop comment text, so a commented-out assertion does not count.

    Line-based and deliberately crude: `//` to end of line (not after a colon,
    so URLs survive), whole lines starting with `#` or `*`, and `/* */` blocks.
    It does not parse strings, so an assertion that exists only inside a string
    literal still counts.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    kept = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("#", "*")):
            continue
        kept.append(re.sub(r"(?<!:)//.*$", "", line))
    return "\n".join(kept)


def has_assertion(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return bool(ASSERTION.search(strip_comments(text)))


def find_test_files(package: Path, ledger: dict) -> list[Path]:
    spec = ledger.get("tests") or {}
    directory = spec.get("dir", "test") if isinstance(spec, dict) else "test"
    patterns = _strings(spec.get("glob") if isinstance(spec, dict) else None) or [
        "*.test.*",
        "test_*.py",
        "*_test.*",
    ]
    root = _inside(package, directory)
    if root is None or not root.is_dir():
        return []
    found = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and any(fnmatch.fnmatch(path.name, p) for p in patterns):
            found.append(path)
    return found


def check_ledger(ledger: dict, audit: Audit) -> tuple[dict, list[dict], list[dict]]:
    """Validate shape. Returns (references by id, claims, mutations)."""
    references: dict[str, dict] = {}
    for entry in ledger.get("references") or []:
        if not isinstance(entry, dict) or not entry.get("id") or not entry.get("path"):
            audit.add("ledger", FAIL, "a reference needs `id` and `path`", str(entry))
            continue
        if entry["id"] in references:
            audit.add("ledger", FAIL, "duplicate reference id", entry["id"])
            continue
        references[entry["id"]] = entry

    claims: list[dict] = []
    seen: set[str] = set()
    for entry in ledger.get("claims") or []:
        if not isinstance(entry, dict) or not entry.get("id"):
            audit.add("ledger", FAIL, "a claim needs an `id`", str(entry))
            continue
        cid = entry["id"]
        if cid in seen:
            audit.add("ledger", FAIL, "duplicate claim id", cid)
            continue
        seen.add(cid)
        if entry.get("kind") not in KINDS:
            audit.add(
                "ledger",
                FAIL,
                f"kind must be one of {', '.join(KINDS)}; got {entry.get('kind')!r}",
                cid,
            )
            continue
        if not isinstance(entry.get("statement"), str) or not entry["statement"].strip():
            audit.add("ledger", FAIL, "a claim needs a `statement`", cid)
            continue
        claims.append(entry)

    mutations: list[dict] = []
    seen_mutations: set[str] = set()
    for entry in ledger.get("mutations") or []:
        if not isinstance(entry, dict) or not entry.get("id"):
            audit.add("ledger", FAIL, "a mutation needs an `id`", str(entry))
            continue
        mid = entry["id"]
        if mid in seen_mutations:
            audit.add("ledger", FAIL, "duplicate mutation id", mid)
            continue
        seen_mutations.add(mid)
        missing = [k for k in ("claim", "file", "find", "replace") if not isinstance(entry.get(k), str)]
        if missing:
            audit.add("ledger", FAIL, f"mutation is missing {', '.join(missing)}", mid)
            continue
        if entry["find"] == entry["replace"]:
            audit.add("ledger", FAIL, "`find` and `replace` are identical", mid)
            continue
        if entry["claim"] not in seen:
            audit.add("ledger", FAIL, f"mutation names unknown claim {entry['claim']!r}", mid)
            continue
        mutations.append(entry)

    if not claims:
        audit.add("ledger", FAIL, "the ledger has no valid claims")
    elif not any(r.check == "ledger" for r in audit.results):
        audit.add(
            "ledger",
            PASS,
            f"{len(claims)} claims, {len(references)} references, {len(mutations)} mutations",
        )
    return references, claims, mutations


def check_asserting(package: Path, ledger: dict, audit: Audit) -> None:
    files = find_test_files(package, ledger)
    if not files:
        audit.add("asserting", FAIL, "no test files found (see `tests.dir` and `tests.glob`)")
        return
    silent = [f for f in files if not has_assertion(f)]
    for path in silent:
        audit.add(
            "asserting",
            FAIL,
            "contains no assertion: it cannot fail",
            str(path.relative_to(package)),
        )
    if not silent:
        audit.add("asserting", PASS, f"{len(files)} test files, each with an assertion")


def check_claims(package: Path, claims: list[dict], mutations: list[dict], audit: Audit) -> None:
    mutated = {m["claim"] for m in mutations}
    for claim in claims:
        cid, kind = claim["id"], claim["kind"]
        if kind in UNCHECKED_KINDS:
            continue
        test = claim.get("test")
        if not isinstance(test, str):
            audit.add("claims", FAIL, f"a {kind} claim needs a `test` file", cid)
            continue
        path = _inside(package, test)
        if path is None or not path.is_file():
            audit.add("claims", FAIL, f"test file {test} does not exist", cid)
            continue
        if not has_assertion(path):
            audit.add("claims", FAIL, f"{test} contains no assertion", cid)
            continue
        if cid in mutated:
            audit.add("claims", PASS, f"{kind}: {test}, with a mutation", cid)
        else:
            audit.add(
                "claims",
                WARN,
                f"{kind}: {test} asserts, but no mutation shows it tests this claim",
                cid,
            )


def check_references(
    package: Path, ledger: dict, references: dict, claims: list[dict], audit: Audit
) -> None:
    used: set[str] = set()
    for claim in claims:
        if claim["kind"] != "reference":
            continue
        rid = claim.get("reference")
        if rid is None:
            # A single published value typed into the test, not a stored table.
            source = claim.get("source")
            if not isinstance(source, str) or not source.strip():
                audit.add(
                    "references",
                    FAIL,
                    "a reference claim needs `reference` (a stored table) or `source` (a citation)",
                    claim["id"],
                )
            else:
                audit.add("references", PASS, f"cited: {source.strip()}", claim["id"])
            continue
        if rid not in references:
            audit.add("references", FAIL, f"names unknown reference {rid!r}", claim["id"])
            continue
        used.add(rid)

    readers = find_test_files(package, ledger)
    spec = ledger.get("tests") or {}
    tests_dir = _inside(package, spec.get("dir", "test") if isinstance(spec, dict) else "test")
    haystack = ""
    if tests_dir is not None and tests_dir.is_dir():
        for path in sorted(tests_dir.rglob("*")):
            if path.is_file() and path.suffix not in {".txt", ".csv", ".dat", ".json"}:
                haystack += path.read_text(encoding="utf-8", errors="replace")
    for claim in claims:
        test = claim.get("test")
        path = _inside(package, test) if isinstance(test, str) else None
        if path is not None and path.is_file() and path not in readers:
            haystack += path.read_text(encoding="utf-8", errors="replace")

    for rid, entry in references.items():
        path = _inside(package, entry["path"])
        if path is None or not path.is_file():
            audit.add("references", FAIL, f"{entry['path']} does not exist", rid)
            continue
        head = "\n".join(
            path.read_text(encoding="utf-8", errors="replace").splitlines()[:HEADER_LINES]
        )
        problems = []
        if not URL.search(head):
            problems.append("no source URL")
        if not DATE.search(head):
            problems.append("no fetch date (YYYY-MM-DD)")
        if path.name not in haystack:
            problems.append("no test reads it")
        if rid not in used:
            problems.append("no claim uses it")
        if problems:
            audit.add("references", FAIL, "; ".join(problems), rid)
        else:
            audit.add("references", PASS, f"{entry['path']}: sourced, dated and read", rid)


def check_coverage(claims: list[dict], audit: Audit) -> None:
    kinds = {c["kind"] for c in claims}
    needs = [
        (
            {"control"},
            "no negative control: nothing shows the picture goes blank when the cause is removed",
        ),
        (
            {"reference", "independent"},
            "no anchor outside the model: every check is the model agreeing with itself",
        ),
        (
            {"convention", "omitted"},
            "no stated limit: a model with nothing approximated or left out is misdescribed",
        ),
    ]
    missing = [message for wanted, message in needs if not kinds & wanted]
    for message in missing:
        audit.add("coverage", FAIL, message)
    if not missing:
        counts = ", ".join(f"{k} {sum(c['kind'] == k for c in claims)}" for k in KINDS if k in kinds)
        audit.add("coverage", PASS, counts)


def run(command: str, cwd: Path, timeout: int) -> tuple[int, str]:
    """Run a shell command. Returns (exit code, combined output); 124 on timeout.

    Python bytecode caching is turned off: a cached module is reused when the
    source keeps its size and timestamp, which a same-length mutation written
    within a second of the baseline run does.
    """
    try:
        done = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout} s"
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def check_quoted(
    package: Path, ledger: dict, claims: list[dict], audit: Audit, run_report: bool, timeout: int
) -> None:
    quotes = [(c["id"], q) for c in claims for q in _strings(c.get("quoted"))]
    if not quotes:
        audit.add("quoted", WARN, "no claim quotes a number, so the prose is not tied to a report")
        return

    docs = ""
    for name in _strings(ledger.get("docs")) or ["README.md"]:
        path = _inside(package, name)
        if path is None or not path.is_file():
            audit.add("quoted", FAIL, f"doc {name} does not exist")
            continue
        docs += path.read_text(encoding="utf-8", errors="replace")

    report = None
    command = (ledger.get("commands") or {}).get("report")
    if run_report:
        if not isinstance(command, str):
            audit.add("quoted", FAIL, "--run-report given but the ledger has no `commands.report`")
        else:
            code, output = run(command, package, timeout)
            if code != 0:
                audit.add("quoted", FAIL, f"report command exited {code}", command)
            else:
                report = output

    undocumented = [(cid, q) for cid, q in quotes if q not in docs]
    for cid, quote in undocumented:
        audit.add("quoted", FAIL, f"{quote!r} is in the ledger but not in the docs", cid)
    if not undocumented:
        audit.add("quoted", PASS, f"{len(quotes)} quoted values appear in the docs")

    if report is None:
        if not run_report:
            audit.add("quoted", SKIP, "report not run (--run-report): the values are unverified")
        return
    unprinted = [(cid, q) for cid, q in quotes if q not in report]
    for cid, quote in unprinted:
        audit.add("quoted", FAIL, f"{quote!r} is not in the report output", cid)
    if not unprinted:
        audit.add("quoted", PASS, f"{len(quotes)} quoted values are printed by the report")


def copy_package(package: Path, destination: Path, links: tuple[str, ...]) -> None:
    """Copy the package for mutation, linking heavy directories instead."""

    def ignore(directory: str, names: list[str]) -> list[str]:
        skipped = [n for n in names if n == ".git"]
        if Path(directory).resolve() == package.resolve():
            skipped += [n for n in names if n in links]
        return skipped

    shutil.copytree(package, destination, ignore=ignore, symlinks=True)
    for name in links:
        source = package / name
        if source.exists():
            os.symlink(source.resolve(), destination / name, target_is_directory=source.is_dir())


def check_mutations(
    package: Path,
    ledger: dict,
    mutations: list[dict],
    audit: Audit,
    run_mutations: bool,
    timeout: int,
) -> None:
    if not mutations:
        audit.add(
            "mutations",
            WARN,
            "no mutations: nothing shows that a test fails when the code is wrong",
        )
        return

    default_command = (ledger.get("commands") or {}).get("test")
    applicable: list[tuple[dict, Path, str]] = []
    for mutation in mutations:
        mid = mutation["id"]
        path = _inside(package, mutation["file"])
        if path is None or not path.is_file():
            audit.add("mutations", FAIL, f"{mutation['file']} does not exist", mid)
            continue
        count = path.read_text(encoding="utf-8").count(mutation["find"])
        if count != 1:
            audit.add(
                "mutations",
                FAIL,
                f"`find` occurs {count} times in {mutation['file']}; it must occur once",
                mid,
            )
            continue
        command = mutation.get("command", default_command)
        if not isinstance(command, str):
            audit.add("mutations", FAIL, "no `command` and no `commands.test`", mid)
            continue
        applicable.append((mutation, path, command))

    if not run_mutations:
        if applicable:
            audit.add(
                "mutations",
                SKIP,
                f"{len(applicable)} mutations apply but were not run (--run-mutations)",
            )
        return

    links = tuple(_strings(ledger.get("link"))) or DEFAULT_LINKS
    baselines: dict[str, int] = {}
    with tempfile.TemporaryDirectory(prefix="sim-audit-") as scratch:
        copy = Path(scratch) / "package"
        copy_package(package, copy, links)
        for mutation, path, command in applicable:
            mid = mutation["id"]
            if command not in baselines:
                baselines[command], _ = run(command, copy, timeout)
            if baselines[command] != 0:
                audit.add(
                    "mutations",
                    FAIL,
                    f"the test command exits {baselines[command]} before any change: {command}",
                    mid,
                )
                continue
            target = copy / path.resolve().relative_to(package.resolve())
            original = target.read_text(encoding="utf-8")
            target.write_text(
                original.replace(mutation["find"], mutation["replace"]), encoding="utf-8"
            )
            try:
                code, _ = run(command, copy, timeout)
            finally:
                target.write_text(original, encoding="utf-8")
            if code == 0:
                audit.add(
                    "mutations",
                    FAIL,
                    f"SURVIVED: the tests still pass with {mutation['file']} changed, "
                    f"so nothing enforces claim {mutation['claim']}",
                    mid,
                )
            elif code == 124:
                audit.add("mutations", FAIL, f"timed out after {timeout} s", mid)
            else:
                audit.add("mutations", PASS, f"killed (exit {code}): {mutation['claim']}", mid)


def audit_package(
    package: Path,
    run_report: bool = False,
    run_mutations: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> Audit:
    ledger = load_ledger(find_ledger(package))
    audit = Audit()
    references, claims, mutations = check_ledger(ledger, audit)
    check_asserting(package, ledger, audit)
    check_claims(package, claims, mutations, audit)
    check_references(package, ledger, references, claims, audit)
    check_coverage(claims, audit)
    check_quoted(package, ledger, claims, audit, run_report, timeout)
    check_mutations(package, ledger, mutations, audit, run_mutations, timeout)
    return audit


def render(audit: Audit, strict: bool) -> str:
    lines = []
    for result in audit.results:
        subject = f" [{result.subject}]" if result.subject else ""
        lines.append(f"{result.status:<4} {result.check:<10}{subject} {result.detail}")
    tally = {s: sum(r.status == s for r in audit.results) for s in (PASS, WARN, SKIP, FAIL)}
    lines.append("")
    lines.append(
        f"{tally[PASS]} pass, {tally[WARN]} warn, {tally[SKIP]} skip, {tally[FAIL]} fail"
        + (" (strict: warnings fail)" if strict else "")
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sim-audit", description="Audit a simulation package against its claim ledger."
    )
    parser.add_argument("package", type=Path, help="directory holding sim-claims.yaml")
    parser.add_argument("--run-report", action="store_true", help="run `commands.report`")
    parser.add_argument("--run-mutations", action="store_true", help="apply each mutation in a copy")
    parser.add_argument("--strict", action="store_true", help="warnings fail")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="seconds per command")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    if not args.package.is_dir():
        print(f"sim-audit: {args.package} is not a directory", file=sys.stderr)
        return 2
    try:
        audit = audit_package(args.package, args.run_report, args.run_mutations, args.timeout)
    except LedgerError as exc:
        print(f"sim-audit: {exc}", file=sys.stderr)
        return 2

    failed = audit.failed(args.strict)
    if args.json:
        print(
            json.dumps(
                {"ok": not failed, "results": [r.as_dict() for r in audit.results]}, indent=2
            )
        )
    else:
        print(render(audit, args.strict))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
