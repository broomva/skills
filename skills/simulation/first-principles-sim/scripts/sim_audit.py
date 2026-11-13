#!/usr/bin/env python3
"""Audit a simulation package against its claim ledger.

A simulation that looks right is evidence that it looks right. This script
checks the part that can be decided without looking: that every claim the
package makes is either enforced by something that can fail, or labelled as
unchecked.

The ledger is `sim-claims.yaml` (or `.json`) in the package directory. It lists
the reference files, the claims, the numbers quoted in prose, and small code
changes ("mutations") that must turn a test red.

Checks:

  ledger       the ledger's entries are well formed and its ids resolve
  asserting    every test file contains an assertion (a test that only prints
               passes whatever the physics does)
  claims       each checked claim names a test file, or a declared gate, that
               exists and asserts
  gates        (--run-gates) each gate's command exits 0
  references   each reference file states a URL and a fetch date, and a test
               reads it (a table nobody loads was retyped); a reference claim
               with no stored table must cite its source
  coverage     the ledger has a negative control, an anchor computed outside
               the model, and at least one stated limit
  quoted       each quoted number appears in the docs, and (--run-report) in
               the standard output of the report command
  suite        (--run-tests) the test command exits 0
  mutations    each mutation applies exactly once to code that is not a test,
               a gate, a registered reference table, or anything in the tests
               directory or a declared support path, and (--run-mutations)
               makes its test command fail

Commands run in a temporary copy of the package, never in the package itself.
A symlink that points inside the package points inside the copy; one that
points elsewhere is followed and its content copied. The directories listed
under `link` are the exception: the copy shares them with the package.

Exit 0 when nothing failed, 1 when a check failed, 2 when the ledger could not
be read or the package could not be copied. A check that needs a flag that was not given reports SKIP, never PASS.
With --strict, WARN and SKIP fail too.

Stdlib only for a JSON ledger; a YAML ledger needs PyYAML.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date
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
#: A ledger can replace this with `tests.assertion` for another framework.
ASSERTIONS = (
    r"\bexpect(_\w+|[A-Z]\w*)?\s*\(",
    r"(?<!console\.)\bassert\w*\s*[(!]",
    r"\bassert\.\w+\s*\(",
    r"\bassert\s+\S",
    r"\bassert_\w+\s+\S",
    r"\bAssert\.\w+\s*\(",
    r"\bXCTAssert\w*\s*\(",
    r"\bdoAssert\b",
    r"\brequire\.(Equal|NotEqual|NoError|Error|True|False|Nil|NotNil|InDelta|Len)\w*\s*\(",
    r"\b(EXPECT|ASSERT|REQUIRE|CHECK)(_[A-Z]+)*\s*\(",
    r"\bBOOST_(CHECK|REQUIRE)\w*\s*\(",
    r"@test\b",
    r"\.should\b",
    r"\bshould(Be|Equal|Throw)\b",
    r"\bshould\s+(be|equal|eq)\b",
    r"\b(strictEqual|deepStrictEqual|deepEqual|notStrictEqual|notEqual)\s*\(",
    r"\bpytest\.raises\b",
    r"\.fail\s*\(",
    r"\bt\.(Error|Errorf|Fatal|Fatalf|Fail|FailNow)\s*\(",
    r"\b(exit|Exit)\s*\(\s*['\"1-9]",
    r"\bexit\s+[1-9]",
    r"\bprocess\.exitCode\s*=\s*[1-9]",
    r"\bthrow\s+\w",
    r"\braise\s+\w",
    r"\bpanic!?\s*\(",
)
ASSERTION = re.compile("|".join(ASSERTIONS))
#: The header of a helper that is named like an assertion. It is removed
#: before matching, so defining `assert_close` does not count as asserting.
DEFINITION = re.compile(
    r"\b(def|function|fn|func|sub|proc)\s+(assert|expect)\w*\s*\("
)
#: Languages whose comments start with `//` or sit in `/* */`.
SLASH_COMMENTS = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".c", ".h", ".cc", ".cpp", ".hpp",
    ".rs", ".go", ".java", ".kt", ".swift", ".cs", ".scala", ".zig",
}  # fmt: skip
#: Languages whose comments start with `#`.
HASH_COMMENTS = {".py", ".rb", ".sh", ".bash", ".jl", ".r", ".pl", ".nim", ".ex", ".exs"}
#: Languages whose comments start with `--`.
DASH_COMMENTS = {".lua", ".hs", ".sql", ".elm"}

URL = re.compile(r"https?://\S+")
DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
#: A fetch date outside these years is a typo or a placeholder.
FIRST_YEAR, LAST_YEAR = 1900, 2099
#: How many leading lines of a reference file may carry its provenance.
HEADER_LINES = 40
#: Directories linked into the copy instead of copied.
DEFAULT_LINKS = ("node_modules", ".venv", "venv", "target")
#: Never copied: version control, and caches that can outlive a source change.
STALE = (".git", "__pycache__", ".pytest_cache")
DEFAULT_TIMEOUT = 600

PASS, FAIL, WARN, SKIP = "PASS", "FAIL", "WARN", "SKIP"


class AuditError(Exception):
    """The audit could not be carried out at all. Exit 2."""


class LedgerError(AuditError):
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
        bad = {FAIL, WARN, SKIP} if strict else {FAIL}
        return any(r.status in bad for r in self.results)


@dataclass
class Ledger:
    """The ledger with its top-level types checked. Entries are checked later."""

    docs: list[str]
    tests_dir: str
    globs: list[str]
    gates: dict[str, str]  # file -> command
    support: list[str]
    assertion: re.Pattern
    commands: dict[str, str]
    links: tuple[str, ...]
    references: list
    claims: list
    mutations: list


# Reading the ledger


def find_ledger(package: Path) -> Path:
    found = [package / name for name in LEDGER_NAMES if (package / name).is_file()]
    if not found:
        raise LedgerError(f"no ledger in {package} (looked for {', '.join(LEDGER_NAMES)})")
    if len(found) > 1:
        raise LedgerError(f"more than one ledger: {', '.join(p.name for p in found)}")
    return found[0]


def _unique_pairs(pairs: list) -> dict:
    """A mapping from `pairs`, refusing a key that appears twice."""
    seen: dict = {}
    for key, value in pairs:
        if key in seen:
            raise LedgerError(f"the ledger has the key {key!r} twice in one mapping")
        seen[key] = value
    return seen


def read_ledger(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise LedgerError(f"{path.name} is not UTF-8: {exc}") from exc
    if path.suffix == ".json":
        try:
            data = json.loads(text, object_pairs_hook=_unique_pairs)
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

        class UniqueKeys(yaml.SafeLoader):
            """A second `claims:` would silently replace the first."""

            def construct_mapping(self, node, deep=False):
                keys = [self.construct_object(key, deep=True) for key, _ in node.value]
                _unique_pairs([(key, None) for key in keys if isinstance(key, (str, int, float))])
                return super().construct_mapping(node, deep)

        try:
            data = yaml.load(text, Loader=UniqueKeys)  # noqa: S506 - a SafeLoader subclass
        except yaml.YAMLError as exc:
            raise LedgerError(f"{path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise LedgerError(f"{path.name}: the top level must be a mapping")
    return data


def _string_list(data: dict, key: str, default: list[str]) -> list[str]:
    """`data[key]` as a list of non-empty strings. A bare string is one item."""
    value = data.get(key, default)
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise LedgerError(f"`{key}` must be a list of non-empty strings")
    return value


def parse_ledger(data: dict) -> Ledger:
    """Check the ledger's top-level types. Raises LedgerError on a wrong shape."""
    tests = data.get("tests", {})
    if not isinstance(tests, dict):
        raise LedgerError("`tests` must be a mapping")
    tests_dir = tests.get("dir", "test")
    if not isinstance(tests_dir, str) or not tests_dir.strip():
        raise LedgerError("`tests.dir` must be a string")
    assertion = ASSERTION
    if "assertion" in tests:
        if not isinstance(tests["assertion"], str):
            raise LedgerError("`tests.assertion` must be a string")
        try:
            assertion = re.compile(tests["assertion"])
        except re.error as exc:
            raise LedgerError(f"`tests.assertion` is not a regular expression: {exc}") from exc

    commands = data.get("commands", {})
    if not isinstance(commands, dict) or not all(
        isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in commands.items()
    ):
        raise LedgerError("`commands` must map names to command strings")

    links = _string_list(data, "link", list(DEFAULT_LINKS))
    for name in links:
        if name in {".", ".."} or "/" in name or "\\" in name:
            raise LedgerError(f"`link` entries are top-level directory names; got {name!r}")

    gates: dict[str, str] = {}
    declared = tests.get("gates", [])
    if not isinstance(declared, list):
        raise LedgerError("`tests.gates` must be a list")
    for gate in declared:
        if (
            not isinstance(gate, dict)
            or not isinstance(gate.get("file"), str)
            or not isinstance(gate.get("command"), str)
            or not gate["file"].strip()
            or not gate["command"].strip()
        ):
            raise LedgerError("each `tests.gates` entry needs a `file` and a `command`")
        gates[gate["file"]] = gate["command"]

    entries = {}
    for key in ("references", "claims", "mutations"):
        value = data.get(key) or []
        if not isinstance(value, list):
            raise LedgerError(f"`{key}` must be a list")
        entries[key] = value

    return Ledger(
        docs=_string_list(data, "docs", ["README.md"]),
        tests_dir=tests_dir,
        globs=_string_list(tests, "glob", ["*.test.*", "test_*.py", "*_test.*"]),
        gates=gates,
        support=_string_list(tests, "support", []),
        assertion=assertion,
        commands=commands,
        links=tuple(links),
        **entries,
    )


def load_ledger(package: Path) -> Ledger:
    return parse_ledger(read_ledger(find_ledger(package)))


# Files


def _inside(package: Path, relative: str) -> Path | None:
    """`relative` resolved under `package`, or None if it leaves it."""
    try:
        target = (package / relative).resolve()
    except (OSError, ValueError):
        return None
    if target != package and package not in target.parents:
        return None
    return target


def has_date(text: str) -> bool:
    """Whether `text` holds a real calendar date, YYYY-MM-DD."""
    for year, month, day in DATE.findall(text):
        try:
            date(int(year), int(month), int(day))
        except ValueError:
            continue
        if FIRST_YEAR <= int(year) <= LAST_YEAR:
            return True
    return False


def _same(a: Path, b: Path) -> bool:
    """Whether two paths are one file, whatever their spelling or letter case."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _within(path: Path, directory: Path) -> bool:
    """Whether `path` is `directory` or sits under it, by file identity."""
    return any(_same(parent, directory) for parent in (path, *path.parents))


def strip_comments(text: str, suffix: str) -> str:
    """Drop comment text, so a commented-out assertion does not count.

    Deliberately crude. For `//` languages: `/* */` blocks, on one line or
    many, whole lines starting with `//`, and `//` to end of line unless it
    follows a colon (so URLs survive). For `#` languages: `#` to end of line,
    unless it sits inside quotes on that line or follows `$`. For `--`
    languages: `--` to end of line. A file of an unknown language loses only
    whole lines that start with a comment marker. Strings are otherwise not
    parsed, so an assertion that exists only inside a string still counts.
    """
    known = suffix in SLASH_COMMENTS or suffix in HASH_COMMENTS or suffix in DASH_COMMENTS
    if suffix in SLASH_COMMENTS:
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        text = re.sub(r"/\*(?:(?!\*/).)*\Z", "", text, flags=re.S)
    kept = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if not known and stripped.startswith(("#", "//", "/*", "*")):
            continue
        if suffix in HASH_COMMENTS:
            line = strip_hash_comment(line)
        if suffix in SLASH_COMMENTS:
            line = re.sub(r"(?<!:)//.*$", "", line)
        if suffix in DASH_COMMENTS:
            line = re.sub(r"--.*$", "", line)
        kept.append(line)
    return "\n".join(kept)


def is_source(path: Path) -> bool:
    """Whether `path` is code in a language whose comments the audit knows."""
    suffix = path.suffix.lower()
    return suffix in SLASH_COMMENTS or suffix in HASH_COMMENTS or suffix in DASH_COMMENTS


def strip_hash_comment(line: str) -> str:
    """`line` up to a `#` that starts a comment.

    A `#` inside quotes on the same line, or straight after `$`, is not one.
    Strings that span lines are not followed.
    """
    quote = ""
    for index, char in enumerate(line):
        escaped = index > 0 and line[index - 1] == "\\"
        if quote:
            if char == quote and not escaped:
                quote = ""
        elif char in "'\"":
            quote = char
        elif char == "#" and not (index > 0 and line[index - 1] == "$"):
            return line[:index]
    return line


def code_text(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return strip_comments(text, path.suffix.lower())


def has_assertion(path: Path, pattern: re.Pattern = ASSERTION) -> bool:
    return bool(pattern.search(DEFINITION.sub("", code_text(path))))


def find_test_files(package: Path, ledger: Ledger) -> list[Path]:
    root = _inside(package, ledger.tests_dir)
    if root is None or not root.is_dir():
        return []
    return [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file() and any(fnmatch.fnmatch(path.name, g) for g in ledger.globs)
    ]


def gate_files(package: Path, ledger: Ledger, audit: Audit) -> list[Path]:
    """Checks the test command does not run, such as a headless render gate."""
    found = []
    for name in ledger.gates:
        path = _inside(package, name)
        if path is None or not path.is_file():
            audit.add("ledger", FAIL, "gate file does not exist inside the package", name)
        else:
            found.append(path)
    return found


def support_files(package: Path, ledger: Ledger, audit: Audit) -> list[Path]:
    """Test helpers and data that live outside the tests directory."""
    found = []
    for name in ledger.support:
        path = _inside(package, name)
        if path is None or not path.exists():
            audit.add("ledger", FAIL, "support path does not exist inside the package", name)
        else:
            found.append(path)
    return found


def check_gates(
    ledger: Ledger, audit: Audit, copy: Path | None, run_gates: bool, timeout: int
) -> None:
    for name, command in ledger.gates.items():
        if not run_gates or copy is None:
            audit.add("gates", SKIP, f"not run (--run-gates): {command}", name)
            continue
        code, _ = run(command, copy, timeout)
        if code == 0:
            audit.add("gates", PASS, f"exit 0: {command}", name)
        elif code == 124:
            audit.add("gates", FAIL, f"timed out after {timeout} s: {command}", name)
        else:
            audit.add("gates", FAIL, f"exit {code}: {command}", name)


# Checks


def check_ledger(ledger: Ledger, audit: Audit) -> tuple[dict, list[dict], list[dict]]:
    """Validate entries. Returns (references by id, claims, mutations)."""
    before = len(audit.results)
    references: dict[str, dict] = {}
    for entry in ledger.references:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("id"), str)
            or not isinstance(entry.get("path"), str)
        ):
            audit.add("ledger", FAIL, "a reference needs a string `id` and `path`", str(entry))
            continue
        if entry["id"] in references:
            audit.add("ledger", FAIL, "duplicate reference id", entry["id"])
            continue
        references[entry["id"]] = entry

    claims: list[dict] = []
    seen: set[str] = set()
    for entry in ledger.claims:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            audit.add("ledger", FAIL, "a claim needs a string `id`", str(entry))
            continue
        cid = entry["id"]
        if cid in seen:
            audit.add("ledger", FAIL, "duplicate claim id", cid)
            continue
        seen.add(cid)
        if not isinstance(entry.get("kind"), str) or entry["kind"] not in KINDS:
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
        quoted = entry.get("quoted", [])
        if not isinstance(quoted, list) or not all(isinstance(q, str) and q.strip() for q in quoted):
            audit.add(
                "ledger",
                FAIL,
                '`quoted` must be a list of non-empty strings; write "9.81", not 9.81',
                cid,
            )
            continue
        claims.append(entry)

    valid_claims = {c["id"] for c in claims}
    mutations: list[dict] = []
    seen_mutations: set[str] = set()
    for entry in ledger.mutations:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            audit.add("ledger", FAIL, "a mutation needs a string `id`", str(entry))
            continue
        mid = entry["id"]
        if mid in seen_mutations:
            audit.add("ledger", FAIL, "duplicate mutation id", mid)
            continue
        seen_mutations.add(mid)
        missing = [
            k for k in ("claim", "file", "find", "replace") if not isinstance(entry.get(k), str)
        ]
        if missing:
            audit.add("ledger", FAIL, f"mutation is missing {', '.join(missing)}", mid)
            continue
        if "command" in entry and not isinstance(entry["command"], str):
            audit.add("ledger", FAIL, "a mutation's `command` must be a string", mid)
            continue
        if entry["find"] == entry["replace"]:
            audit.add("ledger", FAIL, "`find` and `replace` are identical", mid)
            continue
        if entry["claim"] not in valid_claims:
            audit.add("ledger", FAIL, f"mutation names unknown claim {entry['claim']!r}", mid)
            continue
        mutations.append(entry)

    if not claims:
        audit.add("ledger", FAIL, "the ledger has no valid claims")
    elif len(audit.results) == before:
        audit.add(
            "ledger",
            PASS,
            f"{len(claims)} claims, {len(references)} references, {len(mutations)} mutations",
        )
    return references, claims, mutations


def check_asserting(package: Path, ledger: Ledger, tests: list[Path], audit: Audit) -> None:
    if not tests:
        audit.add("asserting", FAIL, "no test files found (see `tests.dir` and `tests.glob`)")
        return
    silent = [f for f in tests if not has_assertion(f, ledger.assertion)]
    for path in silent:
        audit.add(
            "asserting",
            FAIL,
            "contains no assertion: it cannot fail",
            str(path.relative_to(package)),
        )
    if not silent:
        audit.add("asserting", PASS, f"{len(tests)} test files, each with an assertion")


def check_claims(
    package: Path,
    ledger: Ledger,
    claims: list[dict],
    mutations: list[dict],
    checks: list[Path],
    audit: Audit,
) -> None:
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
        if not any(_same(path, check) for check in checks):
            audit.add(
                "claims",
                FAIL,
                f"{test} is neither a test file nor listed under `tests.gates`",
                cid,
            )
            continue
        if not has_assertion(path, ledger.assertion):
            audit.add("claims", FAIL, f"{test} contains no assertion", cid)
            continue
        if cid in mutated:
            audit.add("claims", PASS, f"{kind}: {test}, and a mutation names it", cid)
        else:
            audit.add(
                "claims",
                WARN,
                f"{kind}: {test} asserts, but no mutation shows it tests this claim",
                cid,
            )


def check_references(
    package: Path,
    ledger: Ledger,
    references: dict,
    claims: list[dict],
    checks: list[Path],
    support: list[Path],
    audit: Audit,
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
        if not isinstance(rid, str) or rid not in references:
            audit.add("references", FAIL, f"names unknown reference {rid!r}", claim["id"])
            continue
        used.add(rid)

    # Code that could load a table: the checks, a support file named in the
    # ledger, and source files beside the tests or under a support directory.
    # A manifest, a checksum list or a README that names the table is not code.
    readers = set(checks)
    tests_dir = _inside(package, ledger.tests_dir)
    for place in [tests_dir, *support]:
        if place is None:
            continue
        if place.is_file():
            readers.add(place)
        else:
            readers.update(p for p in place.rglob("*") if p.is_file() and is_source(p))
    # A registered table is data, whatever its suffix: one called `drop.py`
    # that quotes its own URL would otherwise count as naming itself.
    tables = [_inside(package, entry["path"]) for entry in references.values()]
    readers = {p for p in readers if not any(t is not None and _same(p, t) for t in tables)}
    code = "\n".join(code_text(p) for p in sorted(readers))

    for rid, entry in references.items():
        path = _inside(package, entry["path"])
        if path is None or not path.is_file():
            audit.add("references", FAIL, f"{entry['path']} does not exist in the package", rid)
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            audit.add("references", FAIL, f"{entry['path']} cannot be read: {exc.strerror}", rid)
            continue
        head = "\n".join(text.splitlines()[:HEADER_LINES])
        problems = []
        if not URL.search(head):
            problems.append("no source URL")
        if not has_date(head):
            problems.append("no fetch date (YYYY-MM-DD)")
        if path.name not in code:
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
            "no negative control: nothing shows the effect vanishes when the cause is removed",
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
    """Run a shell command. Returns (exit code, standard output); 124 on timeout.

    The command gets its own process group, and the whole group is killed on a
    timeout, so a compound command leaves no child running. Python bytecode
    caching is turned off: a cached module is reused when the source keeps its
    size and timestamp, which a same-length mutation written within a second of
    the baseline run does.
    """
    process = subprocess.Popen(
        command,
        shell=True,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        errors="replace",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        start_new_session=True,
    )
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        return 124, ""
    return process.returncode, output or ""


def check_quoted(
    package: Path,
    ledger: Ledger,
    claims: list[dict],
    audit: Audit,
    copy: Path | None,
    run_report: bool,
    timeout: int,
) -> None:
    quotes = [(c["id"], q) for c in claims for q in c.get("quoted", [])]
    if not quotes:
        audit.add("quoted", WARN, "no claim quotes a number, so the prose is not tied to a report")
        return

    docs = ""
    for name in ledger.docs:
        path = _inside(package, name)
        if path is None or not path.is_file():
            audit.add("quoted", FAIL, f"doc {name} does not exist in the package")
            continue
        docs += path.read_text(encoding="utf-8", errors="replace")

    undocumented = [(cid, q) for cid, q in quotes if q not in docs]
    for cid, quote in undocumented:
        audit.add("quoted", FAIL, f"{quote!r} is in the ledger but not in the docs", cid)
    if not undocumented:
        audit.add("quoted", PASS, f"{len(quotes)} quoted values appear in the docs")

    if not run_report or copy is None:
        audit.add("quoted", SKIP, "report not run (--run-report): the values are unverified")
        return
    command = ledger.commands.get("report")
    if command is None:
        audit.add("quoted", FAIL, "--run-report given but the ledger has no `commands.report`")
        return
    code, report = run(command, copy, timeout)
    if code != 0:
        audit.add("quoted", FAIL, f"report command exited {code}", command)
        return
    unprinted = [(cid, q) for cid, q in quotes if q not in report]
    for cid, quote in unprinted:
        audit.add("quoted", FAIL, f"{quote!r} is not in the report output", cid)
    if not unprinted:
        audit.add("quoted", PASS, f"{len(quotes)} quoted values are printed by the report")


def copy_package(package: Path, destination: Path, links: tuple[str, ...]) -> None:
    """Copy the package without its caches, linking heavy top-level directories.

    A linked directory is shared with the package: a command that writes a
    cache there writes to the real one. A symlink that points inside the
    package is recreated pointing inside the copy. Any other symlink is
    followed and its content copied.
    """

    internal: list[tuple[Path, Path]] = []  # (link, its target), both inside the package

    def ignore(directory: str, names: list[str]) -> list[str]:
        here = Path(directory)
        # Compiled Python left in the package would be loaded in place of a
        # mutated source of the same size written within the same second.
        skipped = [n for n in names if n in STALE]
        if here.resolve() == package:
            skipped += [n for n in names if n in links and (package / n).is_dir()]
        for name in names:
            link = here / name
            if name in skipped or not link.is_symlink():
                continue
            # `exists` follows the link from its own directory; copytree's own
            # check for a dangling link resolves it from the working directory.
            if not link.exists():
                skipped.append(name)
                continue
            target = link.resolve()
            if target == package or package in target.parents:
                # Recreated below, pointing at the copy of its target. Copied
                # as a separate file, a mutation of the target would be
                # invisible to a test that reads it through the link.
                internal.append((link, target))
                skipped.append(name)
        return skipped

    try:
        # Any other symlink is followed: kept as a link, it would let a command
        # write through it to the real file.
        shutil.copytree(package, destination, ignore=ignore, symlinks=False)
    except (shutil.Error, OSError) as exc:
        raise AuditError(f"cannot copy the package: {exc}") from exc
    for name in links:
        source = package / name
        if source.is_dir() and not os.path.lexists(destination / name):
            os.symlink(source.resolve(), destination / name, target_is_directory=True)
    for link, target in internal:
        # `link` was reached by walking real directories, so its parent is
        # inside the package even when the link's own target is elsewhere in it.
        copied = destination / link.parent.resolve().relative_to(package) / link.name
        aim = destination / target.relative_to(package)
        os.symlink(os.path.relpath(aim, copied.parent), copied, target_is_directory=target.is_dir())


def check_suite(
    ledger: Ledger, audit: Audit, copy: Path | None, run_tests: bool, timeout: int
) -> None:
    command = ledger.commands.get("test")
    if not run_tests or copy is None:
        audit.add("suite", SKIP, "tests not run (--run-tests): they may be red")
        return
    if command is None:
        audit.add("suite", FAIL, "--run-tests given but the ledger has no `commands.test`")
        return
    code, _ = run(command, copy, timeout)
    if code == 0:
        audit.add("suite", PASS, f"exit 0: {command}")
    elif code == 124:
        audit.add("suite", FAIL, f"timed out after {timeout} s: {command}")
    else:
        audit.add(
            "suite",
            FAIL,
            f"exit {code} in a copy of the package: {command}. If it passes in place, "
            "the package depends on files outside its own directory",
        )


def check_mutations(
    package: Path,
    ledger: Ledger,
    references: dict,
    mutations: list[dict],
    checks: list[Path],
    support: list[Path],
    audit: Audit,
    copy: Path | None,
    run_mutations: bool,
    timeout: int,
) -> None:
    if not mutations:
        audit.add(
            "mutations",
            FAIL,
            "no mutations: nothing shows that any test fails when the code is wrong",
        )
        return

    # Tests, gates, everything under the tests directory, declared support
    # paths and registered reference tables: changing any of them turns a test
    # red without touching the code the claim is about.
    protected = [*checks, *support]
    tests_dir = _inside(package, ledger.tests_dir)
    if tests_dir is not None and tests_dir.is_dir():
        protected.append(tests_dir)
    for entry in references.values():
        table = _inside(package, entry["path"])
        if table is not None and table.exists():
            protected.append(table)

    applicable: list[tuple[dict, Path, str]] = []
    for mutation in mutations:
        mid = mutation["id"]
        path = _inside(package, mutation["file"])
        if path is None or not path.is_file():
            audit.add("mutations", FAIL, f"{mutation['file']} does not exist in the package", mid)
            continue
        if any(_within(path, guarded) for guarded in protected):
            audit.add(
                "mutations",
                FAIL,
                f"{mutation['file']} is a test, a gate, test data or a test helper: "
                "a mutation changes the code under test",
                mid,
            )
            continue
        if any(_within(path, package / name) for name in ledger.links):
            audit.add(
                "mutations",
                FAIL,
                f"{mutation['file']} is in a linked directory, which the copy shares "
                "with the package (set `link` in the ledger if it holds source)",
                mid,
            )
            continue
        relative = path.relative_to(package)
        if any(part in STALE for part in relative.parts):
            audit.add("mutations", FAIL, f"{mutation['file']} is in a cache, which is not copied", mid)
            continue
        try:
            count = path.read_text(encoding="utf-8").count(mutation["find"])
        except UnicodeDecodeError:
            audit.add("mutations", FAIL, f"{mutation['file']} is not UTF-8", mid)
            continue
        except OSError as exc:
            audit.add("mutations", FAIL, f"{mutation['file']} cannot be read: {exc.strerror}", mid)
            continue
        if count != 1:
            audit.add(
                "mutations",
                FAIL,
                f"`find` occurs {count} times in {mutation['file']}; it must occur once",
                mid,
            )
            continue
        command = mutation.get("command", ledger.commands.get("test"))
        if command is None:
            audit.add("mutations", FAIL, "no `command` and no `commands.test`", mid)
            continue
        applicable.append((mutation, relative, command))

    if not run_mutations or copy is None:
        if applicable:
            audit.add(
                "mutations",
                SKIP,
                f"{len(applicable)} mutations apply but were not run (--run-mutations)",
            )
        return

    baselines: dict[str, int] = {}
    for mutation, relative, command in applicable:
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
        target = copy / relative
        target.chmod(target.stat().st_mode | stat.S_IWUSR)
        original = target.read_text(encoding="utf-8")
        target.write_text(original.replace(mutation["find"], mutation["replace"]), encoding="utf-8")
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
    run_tests: bool = False,
    run_report: bool = False,
    run_mutations: bool = False,
    run_gates: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> Audit:
    package = package.resolve()
    ledger = load_ledger(package)
    run_tests = run_tests or run_mutations
    audit = Audit()
    references, claims, mutations = check_ledger(ledger, audit)
    tests = find_test_files(package, ledger)
    checks = tests + gate_files(package, ledger, audit)
    support = support_files(package, ledger, audit)
    check_asserting(package, ledger, tests, audit)
    check_claims(package, ledger, claims, mutations, checks, audit)
    check_references(package, ledger, references, claims, checks, support, audit)
    check_coverage(claims, audit)

    with tempfile.TemporaryDirectory(prefix="sim-audit-") as scratch:
        copy = None
        if run_tests or run_report or run_gates:
            copy = Path(scratch) / "package"
            copy_package(package, copy, ledger.links)
        check_quoted(package, ledger, claims, audit, copy, run_report, timeout)
        check_suite(ledger, audit, copy, run_tests, timeout)
        check_gates(ledger, audit, copy, run_gates, timeout)
        check_mutations(
            package, ledger, references, mutations, checks, support, audit, copy,
            run_mutations, timeout,
        )  # fmt: skip
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
        + (" (strict: warnings and skips fail)" if strict else "")
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sim-audit", description="Audit a simulation package against its claim ledger."
    )
    parser.add_argument("package", type=Path, help="directory holding sim-claims.yaml")
    parser.add_argument("--run-tests", action="store_true", help="run `commands.test`")
    parser.add_argument("--run-report", action="store_true", help="run `commands.report`")
    parser.add_argument(
        "--run-mutations", action="store_true", help="apply each mutation (implies --run-tests)"
    )
    parser.add_argument("--run-gates", action="store_true", help="run each gate's command")
    parser.add_argument("--strict", action="store_true", help="warnings and skips fail")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="seconds per command")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    def refuse(message: str) -> int:
        if args.json:
            print(json.dumps({"ok": False, "error": message, "results": []}, indent=2))
        print(f"sim-audit: {message}", file=sys.stderr)
        return 2

    if not args.package.is_dir():
        return refuse(f"{args.package} is not a directory")
    try:
        audit = audit_package(
            args.package,
            run_tests=args.run_tests,
            run_report=args.run_report,
            run_mutations=args.run_mutations,
            run_gates=args.run_gates,
            timeout=args.timeout,
        )
    except AuditError as exc:
        return refuse(str(exc))
    except (OSError, ValueError) as exc:
        return refuse(f"{type(exc).__name__}: {exc}")

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
