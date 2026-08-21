#!/usr/bin/env python3
"""skillify_check — the deterministic "skillify doctor".

Garry Tan's rule: *"A feature that doesn't pass all ten is not a skill. It's
just code that happens to work today."* This script makes that rule
machine-checkable. Given a skill directory, it runs the 10-step skillify
checklist and reports PASS / WARN / SKIP / FAIL per item, exiting non-zero when
a *required* step is not satisfied.

Design note (P20-hardened): a gate that checks only *presence* has a wide
false-PASS surface — an empty `test_x.py` and a syntax-broken `do.py` would sail
through. So this doctor *executes* what it cheaply can:

- Step 2 (code) syntax-checks every script (`py_compile` for .py, `bash -n` for
  .sh; .mjs/.js/.ts via `node --check` when node is available, else skipped).
- Step 3 (tests) requires each test file to be non-empty and contain a real test
  construct (`def test_…`, `assert`, `it(`, `test(`, `describe(`, `@pytest`);
  with `--run-tests` it actually invokes pytest and gates on the result.
- `latent_only: true` is only honored when no deterministic CORE is present.
  Shipping a test or an empty package marker beside a lens is fine; shipping a
  script that does something is a contradiction → FAIL.

Required steps gate the exit code: 1 (SKILL.md contract), 2 (code syntax — unless
genuinely latent), 3 (real unit tests, when code present). Workspace-aware steps
(6 resolver trigger, 7 resolver eval, 10 brain filing) SKIP unless their path
flag is supplied. `--strict` promotes 6/7 to required *and* fails if their path
flag is missing (so strict can't pass while skipping the things strict is for).

Pure-stdlib + optional pyyaml/node; deterministic; zero network. Tier J is the
one exception: its admission record is a YAML contract, so it fails closed
without pyyaml rather than gating what it cannot parse.
"""
from __future__ import annotations

import argparse
import ast
import json
import math
import py_compile
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:  # optional, per the module docstring — YAML evals degrade to a regex scan
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - exercised on stdlib-only machines
    yaml = None  # type: ignore[assignment]

def _ext(path: Path) -> str:
    """The file's suffix, CASEFOLDED. The only way this file asks "what kind of file".

    Every extension match here used to be a raw `.suffix`, case-sensitively, at
    nineteen sites (the count, measured: `git diff | grep -c "^-.*\\.suffix"`). Two of them flipped REQUIRED steps on byte-identical content: a script named
    `scripts/core.PY` was not code, so tier D never syntax-checked it and step 3 said
    "no code to test"; an `evals/broken.YAML` was not an eval artifact, so an
    unparseable file became invisible rather than failing closed. `_is_code_file` had
    already been widened once past "five suffixes" for a related reason — this closes
    the same class at every site rather than at the one in front of us.
    """
    return path.suffix.lower()


def _json_loads(txt: str) -> object:
    """The json entry point. Duplicate keys always refuse; recursion never escapes.

    Three call sites read JSON in this file and, before this, one of them carried the
    duplicate-key hook. The other two decided a REQUIRED gate (`skill.json`'s
    `entrypoint`) and an advisory one. Routing them through one function is what makes
    the guarantee hold for the NEXT reader someone adds — see
    `test_no_reader_bypasses_the_shared_guards`, which fails if a raw `json.loads(`
    appears anywhere outside this function.
    """
    return json.loads(txt, object_pairs_hook=_no_duplicate_pairs)


def _ast_parse(txt: str) -> "ast.AST":
    """`ast.parse`, with the two non-SyntaxError failures folded into SyntaxError.

    `ast.parse` raises `RecursionError` on `x = 1+1+1+…` and `MemoryError: Parser stack
    overflowed` on `not not not …`. Three call sites caught only `SyntaxError`, so a
    hostile or generated script produced a bare traceback and zero checklist lines —
    the same contract violation ("an unverified artifact is reported, never thrown")
    that round 13 fixed at `_substantive` and round 15 at two more sites. Re-raising as
    SyntaxError means every existing handler keeps working and says the true thing: the
    gate could not parse this.
    """
    try:
        return ast.parse(txt)
    except (RecursionError, MemoryError) as e:
        raise SyntaxError(f"too deeply nested to parse ({type(e).__name__})") from e


CODE_EXTS = {".py", ".sh", ".mjs", ".js", ".ts"}
_TEST_CODE_EXTS = ("py", "sh", "mjs", "js", "ts")
PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"

# Deepest nesting `_internal_ref_issues._walk` will descend before giving up. This is
# now its ONLY consumer: `_substantive` and `_walk_for_trigger_keys` dropped their caps
# in round 18, because a cap makes the answer a function of the traversal budget and a
# memo then caches it as a property of the node. `_walk` keeps one because its input is
# JSON, which cannot alias, so a visited set would be machinery for an unreachable case.
_MAX_NESTING = 100


# --- frontmatter -------------------------------------------------------------

# Fence padding is spaces and tabs — NOT `[^\S\n]`,
# which also admits form-feed, vertical-tab and NBSP. Those matched here and
# then failed inside PyYAML with a ReaderError, so the gate blamed the YAML for
# a fence the matcher should never have accepted. No `\r` either: `_read` uses
# `read_text()`, whose universal-newline handling turns CRLF (and a lone CR)
# into `\n` before this pattern is applied, so a CR here could never match.
# Round 11 kept one and justified it as CRLF support — CRLF does work, but
# normalization is what does it, not the regex.
_FRONTMATTER_RE = re.compile(r"^\ufeff?---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)", re.DOTALL)


def _count_top_level_key(block: str, key: str) -> int | None:
    """Occurrences of `key` at the TOP LEVEL of a frontmatter block.

    Returns None when it cannot be determined (no pyyaml, or the block does not
    parse) — the caller must then report the check as unperformed rather than guess.

    This was a line-walking regex, twice. Both versions lost the same way, and it is
    the same way the deleted prose heuristics lost: a hand-rolled scanner cannot read
    a structured language. It counted `outcome:` appearing inside a multi-line quoted
    scalar, missed a flow mapping `{outcome: rejected}`, missed a list item, and could
    not tell a nested key from a top-level one without an indentation rule that then
    broke on something else. Every one of those was a FALSE REJECT of valid YAML.

    `yaml.compose()` returns the node tree with duplicate keys PRESERVED (unlike
    `safe_load`, which silently keeps the last), so the question is answered by the
    parser that defines the language rather than by a pattern approximating it.
    """
    if yaml is None:
        return None
    try:
        node = yaml.compose(block)
    except Exception:
        return None
    if not isinstance(node, getattr(yaml, "MappingNode", ())):
        return 0
    return sum(1 for k, _ in node.value
               if str(getattr(k, "value", "")).strip().lower() == key)


def _duplicate_top_level_keys(block: str) -> tuple[str, list[tuple[str, int]]]:
    """Every top-level key declared more than once, with its count.

    Returns `(status, duplicates)` where status is one of:

      * `"ok"`          — the block parsed; `duplicates` is authoritative
      * `"no-parser"`   — pyyaml is absent, so the question cannot be asked at all
      * `"unparseable"` — a parser EXISTS and the block did not parse

    Collapsing the last two into "no duplicates" is what made this bypassable, and the
    tri-state exists to prevent exactly that. `parse_frontmatter` falls back to a
    hand-rolled scanner when YAML rejects a block, and that scanner resolves duplicates
    last-wins. So a `tier: J` / `tier: D` pair plus ONE malformed line —

        tier: J
        tier: D
        broken: [

    — disabled the duplicate check (compose raised, the check reported "no duplicates")
    while value extraction happily produced `tier: D`. Step 2 said "tier D (declared)"
    and PASSED, with the tier-J gate never run: a required gate bypassed by adding a
    broken line.

    Two readers of the same bytes that disagree is worse than one reader that refuses.
    """
    if yaml is None:
        return "no-parser", []
    try:
        node = yaml.compose(block)  # M64 anchor: compose, not safe_load
    except Exception:
        return "unparseable", []
    if not isinstance(node, getattr(yaml, "MappingNode", ())):
        return "ok", []
    counts: dict[str, int] = {}
    for k, _ in node.value:
        name = str(getattr(k, "value", "")).strip().lower()
        counts[name] = counts.get(name, 0) + 1
    return "ok", sorted(((k, n) for k, n in counts.items() if n > 1), key=lambda kv: kv[0])


def _frontmatter_match(text: str):
    """The ONE frontmatter matcher. Tolerates a leading BOM and a closing fence that
    ends the file or carries trailing spaces.

    There used to be three near-copies of `re.match(r"^---\n(.*?)\n---")`, and a BOM
    fix applied to one of them left the other two behind — twice in this arc a fix
    landed at a single site while its sibling kept the old behaviour. One matcher is
    the structural answer to that, not a third careful edit.
    """
    return _FRONTMATTER_RE.match(text)


# How the frontmatter was actually read. The only distinction that matters to a gate is
# whether the HAND-ROLLED SCANNER RAN, because that is the one state in which two
# readers of the same bytes disagree — and a gate keyed on any other condition will
# miss most of it. P20 round 13 keyed the refusal on `yaml.compose` raising; round 14
# showed that is the wrong parser. `compose` builds a node tree without CONSTRUCTING
# values, so `tier: J` + `extra: {x: !!foo 1,` + `tier: D` composes fine (one top-level
# `tier`, value J) while `safe_load` raises ConstructorError — the scanner then took
# last-wins `tier: D` and the skill passed as tier D with the J gate never run.
FM_ABSENT, FM_YAML, FM_FALLBACK, FM_NO_PARSER = "absent", "yaml", "fallback", "no-parser"


def _scan_frontmatter(block: str) -> dict:
    """The hand-rolled, scalar-only reader. Only ever used when YAML could not."""
    fm: dict[str, str] = {}
    for line in block.splitlines():
        if line[:1] in (" ", "\t") or line.lstrip().startswith("#"):
            continue  # indented continuation / comment — not a key
        if ":" in line:
            key, _, val = line.partition(":")
            val = val.strip()
            if not val.startswith(("\"", "'")):
                # YAML: " #" begins a comment on a plain scalar. Without this the
                # template documented in this very skill — `outcome: admitted
                # # or: rejected` — parsed as the literal 'admitted # or: rejected'
                # on any machine without pyyaml.
                val = re.split(r"\s+#", val, 1)[0].strip()
            fm[key.strip()] = val.strip("\"'")
    return fm


def parse_frontmatter_status(md_path: Path) -> tuple[str, dict | None]:
    """`(status, frontmatter)`, where status says WHICH reader produced the dict.

    `FM_FALLBACK` is the load-bearing one: a YAML parser is installed and it refused
    the block, so the scalar-only scanner below took over and may now report a
    different value for the same key. Every gate that reads a declaration must refuse
    on it rather than trust whichever reader answered.
    """
    try:
        # errors="replace": invalid UTF-8 must fail CLOSED (no frontmatter -> step 1
        # FAIL), never raise. A single 0xFF byte in one SKILL.md used to abort the
        # whole --survey run with a UnicodeDecodeError.
        text = md_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return FM_ABSENT, None
    m = _frontmatter_match(text)
    if not m:
        return FM_ABSENT, None
    block = m.group(1)
    if yaml is None:
        return FM_NO_PARSER, _scan_frontmatter(block)
    try:
        data = yaml.safe_load(block)
    except Exception:
        return FM_FALLBACK, _scan_frontmatter(block)
    if isinstance(data, dict):
        return FM_YAML, {k: (v if isinstance(v, str) else str(v)) for k, v in data.items()}
    if data is None and not block.strip():
        # An empty block is well-formed YAML that happens to be empty. Calling it a
        # parse failure would misdiagnose the ordinary "no frontmatter keys" case,
        # which step 1 already reports precisely.
        return FM_YAML, {}
    # Parsed, but not into a mapping (a list, a bare scalar). The scanner is about to
    # invent keys the parser does not agree exist.
    return FM_FALLBACK, _scan_frontmatter(block)


def parse_frontmatter(md_path: Path) -> dict | None:
    """Return the top YAML frontmatter as a flat str dict, or None if absent.

    Thin wrapper: callers that only need the values keep working unchanged. Callers
    that GATE on a value must use `parse_frontmatter_status` and refuse on
    `FM_FALLBACK` — see `_frontmatter_disagreement_issue`.
    """
    return parse_frontmatter_status(md_path)[1]


def _frontmatter_disagreement_issue(path: Path, what: str) -> str | None:
    """Refuse when the YAML parser rejected the block and the scanner took over.

    Keyed on the condition that ACTUALLY produces two disagreeing readers, not on a
    proxy for it. The message deliberately does not name duplicate keys: the round-13
    version did, and told every author with an unquoted colon in `description:` that
    their duplicate keys were being resolved last-wins, which is a misdiagnosis.
    """
    status, _ = parse_frontmatter_status(path)
    if status != FM_FALLBACK:
        return None
    return (f"{what} does not parse as YAML. A parser is installed and rejected the "
            "block, so the gate fell back to a line scanner that reads it differently "
            "— a declaration the scanner sees may not be the one YAML sees, and no "
            "gate can be trusted on the difference. Fix the YAML")


# --- skills.sh installability (the publish target) ---------------------------

def _skillsh_frontmatter_issue(skill_dir: Path) -> str | None:
    """Detect the skills.sh silent-parser-killer. The real breaker (verified
    against the live vercel-labs/skills parser) is a YAML **block-sequence item
    whose value has a quoted scalar immediately followed by a comma** (`- "a", …`)
    — it makes the parser discard the WHOLE frontmatter → "No valid skills found"
    even with a valid name+description.

    NOT breakers (must not be flagged): a single quoted string (`- "one"`), plain
    comma-lists (`- a, b, c`), and quotes inside a `|`/`>` block scalar body (a
    `description:` block with bulleted prose is extremely common). So we exclude
    block-scalar bodies and require the quote-then-comma signature — not a raw
    ≥2-quote count. (Source: skills-sh.md KG entity + P20 v0.2 review.)
    """
    try:
        text = (skill_dir / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = _frontmatter_match(text)
    if not m:
        return None
    quote_comma = re.compile(r'(?:"[^"]*"|\'[^\']*\')\s*,')
    block_indent: int | None = None
    for raw in m.group(1).splitlines():
        indent = len(raw) - len(raw.lstrip(" "))
        if block_indent is not None:  # inside a block-scalar body
            if raw.strip() == "" or indent > block_indent:
                continue
            block_indent = None  # dedented back out
        if re.search(r":\s*[|>][+-]?\d*\s*$", raw):  # this line opens a block scalar
            block_indent = indent
            continue
        if re.match(r"^\s*-\s", raw) and quote_comma.search(raw):
            return raw.strip()
    return None


_BUNDLED_DIRS = {
    "scripts", "references", "assets", "tests",
    "Scripts", "References", "Assets", "Workflows", "src",
}


def _repo_root_bundled_dirs_issue(skill_dir: Path) -> str | None:
    """FAIL if the skill is a git REPO ROOT carrying bundled dirs (scripts/, …).

    BRO-1561: a remote `npx skills add <owner>/<repo>` special-cases a repo-root
    SKILL.md and copies ONLY that file — bundled dirs are silently dropped, so the
    skill installs non-functional (its SKILL.md points at a missing scripts/<x>).
    `--list` passes anyway (it parses frontmatter, never the copy path), so this
    structural check is the gate `--list` cannot be. Fix: put the skill in a
    `skills/<name>/` subdir (the Agent Skills standard layout) — a subdir is a
    clean skill folder and is fully copied.

    Only fires when skill_dir is the git toplevel (a repo root); a `skills/<name>/`
    subdir of a repo is the correct layout and passes.
    """
    try:
        top = subprocess.run(
            ["git", "-C", str(skill_dir), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        is_repo_root = top.returncode == 0 and Path(top.stdout.strip()) == skill_dir.resolve()
    except Exception:
        is_repo_root = (skill_dir / ".git").is_dir()
    if not is_repo_root:
        return None
    bundled = sorted(d.name for d in skill_dir.iterdir() if d.is_dir() and d.name in _BUNDLED_DIRS)
    if not bundled:
        return None
    return (
        f"skill is a repo root with bundled dir(s) {bundled} — a remote `npx skills add` "
        f"drops them (only SKILL.md installs). Move the skill into `skills/{skill_dir.resolve().name}/`."
    )


def _list_output_has(out: str, name: str) -> bool:
    """The skill name must appear as a LISTED entry line (box-drawing/bullet
    prefix, name alone on the line) — NOT merely somewhere in a sibling skill's
    description prose or an error message (P20 v0.2: that fallback was a
    false-PASS that green-lit a broken skill)."""
    return bool(re.search(rf"^[\s│|>*•├└─▸▪\-]*{re.escape(name)}\s*$", out, re.M))


def _skillsh_list_has(target: str, name: str) -> tuple[bool, str]:
    """Run `npx skills add <target> --list` and assert the skill name is listed —
    the non-mutating parse check that exercises the exact clone+parse path
    skills.sh uses on install. `target` is 'owner/repo' or a local path. Network."""
    if not shutil.which("npx"):
        return False, "npx not available (cannot verify skills.sh install)"
    try:
        r = subprocess.run(["npx", "-y", "skills", "add", target, "--list"],
                           capture_output=True, text=True, timeout=180)
    except (subprocess.TimeoutExpired, OSError) as e:
        return False, f"`npx skills add {target} --list` failed: {e}"
    if r.returncode != 0:  # the --list itself failed — don't trust its output (CodeRabbit #1)
        return False, f"`npx skills add {target} --list` exited {r.returncode} (clone/parse failed)"
    found = _list_output_has(r.stdout + r.stderr, name)
    return found, f"'{name}' {'found' if found else 'NOT found'} in `npx skills add {target} --list`"


# --- file classification (recursive within scripts/ & tests/) ----------------

def _is_test_file(name: str) -> bool:
    """True for genuine test files only — `.test.` counts solely for code exts,
    so a data fixture like `fixtures.test.json` is NOT mistaken for a test."""
    # THREE hand-rolled extension idioms lived here, none of them routed through
    # `_ext`, so casefolding landed on `_is_code_file` and not on its partner: a
    # `tests/test_core.PY` containing a real test was told "no tests/ — the 'works
    # today' trap". The source scan could not see it either, because it greps for the
    # literal `.suffix`, which never appeared here. Lowercase the name once, up front.
    lowered = name.lower()
    ext = _ext(Path(lowered)).lstrip(".")
    if lowered.startswith("test_") and ext in _TEST_CODE_EXTS:
        return True
    if any(lowered.endswith(f"_test.{e}") for e in _TEST_CODE_EXTS):
        return True
    # A fourth copy of _TEST_CODE_EXTS used to be spelled out here as a regex literal;
    # built from the constant instead so it cannot drift the day a suffix is added.
    return bool(re.search(r"\.test\.(" + "|".join(sorted(_TEST_CODE_EXTS)) + r")$", lowered))


def _iter_files(skill_dir: Path, subdirs: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    for sub in subdirs:
        d = skill_dir / sub if sub else skill_dir
        if not d.is_dir():
            continue
        it = d.rglob("*") if sub else d.iterdir()  # recurse into named subdirs only
        for p in it:
            if p.is_file() and "__pycache__" not in p.parts:
                out.append(p)
    return out


_COMMENT_PREFIXES = ("#", "//", "/*", "*", "*/", "--", '"""', "'" * 3)


def _has_executable_content(path: Path) -> bool:
    """At least one statement that is not a docstring, a comment, or a shebang.

    A file containing only `# TODO: implement core` is not a deterministic core, and
    neither is one containing only a module docstring saying the same thing — the
    line-prefix check missed the second because docstring BODY lines carry no comment
    marker. Python is decided by AST; other languages by stripping block and line
    comments.

    This is a FLOOR on substance, deliberately NOT a judgement about whether the code
    does anything useful — that is undecidable, and a gate pretending otherwise
    invites an arms race it loses every round.
    """
    txt = _read(path)
    if txt is None:
        return False
    if not txt.strip():
        return False
    head = txt.splitlines()[:1]
    m = _SHEBANG_RE.match(head[0]) if head else None
    is_py = _ext(path) == ".py" or (m and m.group(1).lower() in _PY_INTERPRETERS)
    if is_py:
        try:
            body = _ast_parse(txt).body
        except SyntaxError:
            return True  # broken syntax is step 2's other branch, not emptiness
        if body and isinstance(body[0], ast.Expr) and isinstance(
                getattr(body[0], "value", None), ast.Constant) and isinstance(
                body[0].value.value, str):
            body = body[1:]  # drop the module docstring
        return bool(body)
    stripped = re.sub(r"/\*.*?\*/", "", txt, flags=re.DOTALL)
    stripped = re.sub(r"(?s)<#.*?#>", "", stripped)
    for ln in stripped.splitlines():
        t = ln.strip()
        if not t or t.startswith("#!"):
            continue
        if not t.startswith(_COMMENT_PREFIXES):
            return True
    return False


# Package plumbing, never a deterministic core. Casefolded like every other name
# comparison in this file — `CONFTEST.PY` was counted as shippable code.
_PACKAGE_PLUMBING = {"__init__.py", "conftest.py", "setup.py"}

# Round 20 excluded ALL of _PACKAGE_PLUMBING from the core and round 21 showed that
# was too wide in one direction and too narrow in another. `setup.py` and
# `__init__.py` are NAMED for packaging but routinely hold real logic — excluding
# them turned a passing tier-D skill into "cannot classify", and (worse) hid a real
# core from the `latent_only` contradiction, flipping a required FAIL to a whole-gate
# PASS. `conftest.py` is different in kind: it is pytest's own configuration, it is
# test-side by definition, and nothing else imports it.
#
# So the name-based rule is narrowed to the one file where the name really does
# determine the role, and the empty-marker case — the reason `__init__.py` was in
# here — is handled by SUBSTANCE instead, which is what it always was.
_TEST_INFRA = {"conftest.py"}


def _is_code_file(skill_dir: Path, f: Path) -> bool:
    """Code = a recognized extension, OR an extensionless EXECUTABLE under scripts/.
    `scripts/run` with a shebang is a deterministic core by any reading; keying purely
    off five suffixes let it ship untested ("tests whenever code ships" quietly meant
    "whenever a .py/.sh/.mjs/.js/.ts ships")."""
    # LOCATION DECIDES, and it decides FIRST. Anything shipped under scripts/ is a
    # script — no name exempts it, not a test name and not package plumbing.
    #
    # Round 18 put the name checks ahead of the location check and thereby kept two
    # fail-open holes it claimed to close: a broken `scripts/Setup.py` or
    # `scripts/CONFTEST.PY` was still never syntax-checked (rc 1 -> rc 0). It also
    # opened a worse one, because `_test_files` scans scripts/ too: a lone
    # `scripts/test_only.py` became the deterministic core AND its own unit test, so a
    # skill shipping no core at all inferred tier D and passed steps 2 and 3 together.
    # That is the case `test_tier_d_declared_without_code_fails` calls the one thing
    # the gate must not permit. See `_test_files`, which now refuses the same overlap
    # from the other side — a file cannot be both the core and the proof of the core.
    under_scripts = f.is_relative_to(skill_dir / "scripts")
    if not under_scripts and (f.name.lower() in _PACKAGE_PLUMBING or _is_test_file(f.name)):
        return False
    if _ext(f) in CODE_EXTS:
        return True
    return (not _ext(f) and under_scripts and bool(f.stat().st_mode & 0o111))


def _code_files(skill_dir: Path) -> list[str]:
    found = set()
    for f in _iter_files(skill_dir, ("scripts", "")):
        try:
            if _is_code_file(skill_dir, f):
                found.add(str(f.relative_to(skill_dir)))
        except OSError:
            continue
    return sorted(found)


def _core_files(skill_dir: Path) -> list[str]:
    """Shipped code that is NOT a test — what tier D is inferred from.

    `_code_files` is deliberately wider: everything under scripts/ is syntax-checked,
    test-named or not, because a broken `scripts/test_helper.py` that no checker reads
    is how a required step passed on a file that does not parse.

    Two things disqualify a shipped file from being the core, and both were found
    the hard way. It cannot be a TEST (round 19) and it cannot be EMPTY (round 20) —
    `scripts/conftest.py` is excluded as test infrastructure, and an empty
    `scripts/__init__.py` is excluded for having nothing in it, not for its name.

    `_is_code_file` still lets LOCATION decide first, so all of these are syntax-
    checked as shipped code whatever they are called. Being code and being a core are
    different questions; five call sites turn on the second one.

    The core is narrower, and the difference is the whole point. A lone
    `scripts/test_only.py` used to be BOTH: step 2 inferred tier D from it and step 3
    reported "1 real test file" about the same bytes, so a skill shipping nothing but a
    test passed both required steps — the case
    `test_tier_d_declared_without_code_fails` calls the one thing the gate must not
    permit. A file cannot be the artifact and the proof of the artifact at once.
    """
    return [c for c in _core_candidates(skill_dir)
            if _has_executable_content(skill_dir / c)]


def _is_definitely_a_test(path: Path) -> bool:
    """A STRICTER test detector, used only where a wrong answer excuses a file.

    `_is_real_test` is an AST walk for Python — reliable — but a regex everywhere
    else, and its bash pattern counts `ok()` / `fail()` helper definitions. Those are
    ordinary shell logging helpers: across this roster the pattern calls an
    installer, a publisher, a setup script and an audit script "tests".

    Reporting that a skill has tests can live with that. Excusing a file from the
    `latent_only` contradiction and from `require_tests` cannot, because there the
    error direction is fail-OPEN — round 26 shipped a working publisher named
    `scripts/test_publish.sh` past a clean gate on exactly this.

    So for non-Python, the weak alternation does not count here: a strong construct
    is required (an assert, a bats `@test`, or pass/fail accounting). Python is
    unchanged, because the AST answer is not a guess.
    """
    if _ext(path) == ".py":
        return _is_real_test(path)
    if not _is_real_test(path):
        return False
    try:
        txt = _strip_code_noise(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return False
    return bool(_STRONG_TEST_CONSTRUCT.search(txt))


def _deterministic_scripts(skill_dir: Path) -> list[str]:
    """Any shipped non-test script with something in it — deliberately WIDER than
    the core, and used only by the `latent_only` contradiction.

    `latent_only: true` claims the skill ships nothing deterministic. Answering that
    with `core` let a real, imported module pass by being named `conftest.py`: the
    core excludes pytest configuration by name, so the claim went unchallenged. The
    exclusion is right for INFERRING a tier and wrong for REFUTING a denial, which is
    the tell that these were always two questions.

    Used by BOTH refutations — the `latent_only` contradiction and `require_tests`.
    (An earlier docstring said "used only by the latent_only contradiction"; step 3
    became a consumer in the same round and the sentence was not updated.)

    A file is excluded here only if BOTH predicates agree: the name says test AND
    the structure contains one. Requiring both is what makes the exclusion narrow,
    and narrow is the safe direction for a refutation — fewer things escape it.

    Neither predicate alone survives contact. By NAME only (round 24):
    `scripts/test_helpers.py` holding production logic and no test at all was
    excluded, so a `latent_only` lens shipping it passed the whole gate. By ROLE
    only (round 25): `_is_real_test` is an AST walk for Python but a REGEX for
    everything else, and `test` is a shell builtin — it called the real
    `blog-post/scripts/publish.sh` a test and moved the roster, which is a fail-open
    for every shell script in the repo.

    Also excludes empty files — a package marker is not deterministic anything.
    """
    return [c for c in _code_files(skill_dir)
            if not (_is_test_file(Path(c).name) and _is_definitely_a_test(skill_dir / c))
            and _has_executable_content(skill_dir / c)]


def _core_candidates(skill_dir: Path) -> list[str]:
    """Everything that COULD be a core: shipped code that is neither a test nor
    pytest's own infrastructure. Separate from `_core_files` because the difference
    between the two — candidates that turned out to be empty — is exactly what the
    "an empty file is not a core" message needs to name.
    """
    return [c for c in _code_files(skill_dir)
            if not _is_test_file(Path(c).name)
            and Path(c).name.lower() not in _TEST_INFRA]


def _test_files(skill_dir: Path, kind: str = "") -> list[str]:
    """Test files, wherever they live — INCLUDING under scripts/.

    A first attempt at the overlap problem excluded `scripts/` here. That was a false
    reject, and the roster said so: three real skills keep their only tests beside the
    code they test (`kg/scripts/test_kg.py`, `what/scripts/test_what_concepts.py`,
    `finance-substrate/scripts/test_runtime_guard.py`), and two of them lost a required
    step over nothing but file placement. Refusing a real test for its location is the
    mirror image of the bug it was meant to fix.

    The overlap is a narrower property and it belongs where the CORE is decided, not
    here: see `_core_files`. A test-named script is a test AND is syntax-checked as
    shipped code; what it cannot be is the thing it is testing.
    """
    found = {
        str(f.relative_to(skill_dir))
        for f in _iter_files(skill_dir, ("tests", "scripts", ""))
        if _is_test_file(f.name) and (not kind or kind in f.name.lower())
    }
    return sorted(found)


# --- execution checks (presence is not correctness) --------------------------

_JS_TEST_CONSTRUCT = re.compile(r"\b(it|test|describe)\s*\(|\bassert\b|\bexpect\(")

# Bash test suites (e.g. cross-review's tests/*.test.sh) define ok()/fail() helpers
# + PASS/FAIL accounting rather than JS/py constructs; recognize them too.
# The subset of the bash pattern that cannot be an ordinary logging helper. Used by
# `_is_definitely_a_test`, where a false positive is a fail-open rather than a note.
_STRONG_TEST_CONSTRUCT = re.compile(
    r"\bassert\w*\b"
    r"|^\s*@test\b"
    r"|\b(?:PASS|FAIL|PASSED|FAILED|TESTS_RUN)\s*=\s*0\b",
    re.MULTILINE,
)

_BASH_TEST_CONSTRUCT = re.compile(
    r"\bassert\w*\b"                                          # assert / assert_eq / assertEquals
    r"|^\s*@test\b"                                           # bats
    r"|\b(?:ok|pass|fail|expect|check)\s*\(\s*\)"             # ok()/fail()/pass() test-helper defs
    r"|\b(?:PASS|FAIL|PASSED|FAILED|TESTS_RUN)\s*=\s*0\b"     # pass/fail accounting counters
    r"|\b(?:run_test|test_case|it_should)\b",
    re.IGNORECASE | re.MULTILINE,
)


def _is_py_test_fn(name: str) -> bool:
    return name == "test" or name.startswith("test_")


def _strip_code_noise(txt: str) -> str:
    """Best-effort removal of string literals (so tokens inside them don't count)
    then line comments — for the non-Python regex path (N1)."""
    txt = re.sub(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`(?:[^`\\]|\\.)*`', "", txt)
    return "\n".join(line.split("#", 1)[0].split("//", 1)[0] for line in txt.splitlines())


def _is_real_test(path: Path) -> bool:
    """A file is a real test only if it *structurally* contains a test — not if
    the words 'def test_' / 'assert' merely appear in a string or comment (N1).

    Python: AST (immune to string/comment false positives) — a `test`/`test_*`
    function, or a `Test*` class that actually contains a test method.
    Other languages: regex over string- AND comment-stripped source.
    """
    try:
        txt = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if not txt.strip():
        return False
    if _ext(path) == ".py":
        try:
            tree = _ast_parse(txt)
        except SyntaxError:
            return False
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_py_test_fn(node.name):
                return True
            if isinstance(node, ast.ClassDef) and node.name.startswith("Test") and any(
                isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_py_test_fn(b.name)
                for b in node.body
            ):
                return True
        return False
    stripped = _strip_code_noise(txt)
    if _ext(path) == ".sh":
        return bool(_BASH_TEST_CONSTRUCT.search(stripped))
    return bool(_JS_TEST_CONSTRUCT.search(stripped))


# --- trigger evals (step 5): grade the LATENT half ---------------------------
#
# A skill's deterministic half (scripts) fails loudly; its latent half — whether
# the description fires on a real request and stays silent on a near-miss —
# fails silently. An eval artifact that asserts nothing about triggering leaves
# that half ungated, so step 5 must inspect content, not just presence.
#
# Keys are drawn from the two schemas actually in use here: Schmid's prompt-set
# convention (`should_trigger`) and role-x's resolver evals (`should_fire` /
# `should_not_fire`, roles/<lens>.eval.yaml).
TRIGGER_ASSERTION_KEYS = frozenset({
    "should_trigger", "should_not_trigger", "shouldTrigger", "shouldNotTrigger",
    "should_fire", "should_not_fire", "negative_case",
})

_TRIGGER_ASSERTION_RE = re.compile(
    r"[\"']?(" + "|".join(sorted(TRIGGER_ASSERTION_KEYS)) + r")[\"']?\s*[:=]",
)

_EVAL_DATA_EXTS = {".json", ".yaml", ".yml", ".jsonl", ".toml"}


def _eval_files(skill_dir: Path) -> list[str]:
    """Every candidate eval artifact: files named *eval* under scripts//tests/,
    plus anything inside an evals/ directory. Presence only — see
    _is_trigger_eval for whether it actually asserts anything."""
    found = {str(f.relative_to(skill_dir)) for f in _iter_files(skill_dir, ("tests", "scripts"))
             if "eval" in f.name.lower()}
    evals_dir = skill_dir / "evals"
    if evals_dir.is_dir():
        found |= {
            str(f.relative_to(skill_dir))
            for f in evals_dir.rglob("*")
            if f.is_file() and "__pycache__" not in f.parts
        }
    return sorted(found)


def _is_trigger_eval(path: Path) -> bool:
    """True only if the artifact actually asserts trigger behaviour.

    An EMPTY evals/ dir, a README, or a prompt set with no should_trigger key all
    return False — the whole point of the check. For structured data we parse and
    walk, so the key must be a real key rather than a word in some prose blob; for
    code/markdown we fall back to a regex over comment/string-stripped source,
    matching how _is_real_test treats non-Python languages.
    """
    try:
        txt = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if not txt.strip():
        return False

    if _ext(path) == ".json":
        try:
            return _walk_for_trigger_keys(_json_loads(txt))
        # One clause, because `_DuplicateKey` IS a ValueError. Round 17 added a separate
        # `except _DuplicateKey` above this and wrote a comment claiming it changed the
        # outcome; it did not — renaming it to an exception that is never raised leaves
        # all tests green, which is the definition of inert. The honest statement is the
        # one below: step 5 is advisory, and a file whose keys cannot be trusted is not
        # counted as a clean trigger eval. The duplicate itself is reported by
        # `_load_data` for anything under evals/, and is NOT reported for eval-shaped
        # files elsewhere — a real gap, but an advisory-only one.
        except (ValueError, RecursionError):
            return False
    if _ext(path) in {".yaml", ".yml"}:
        if yaml is not None:
            try:
                return _walk_for_trigger_keys(yaml.safe_load(txt))
            except Exception:
                return False
        # No PyYAML: fall through to the regex rather than silently reporting
        # "no trigger eval" for a file we simply could not parse.
    if _ext(path) in _EVAL_DATA_EXTS - {".json", ".yaml", ".yml"}:
        return bool(_TRIGGER_ASSERTION_RE.search(txt))
    return bool(_TRIGGER_ASSERTION_RE.search(_strip_code_noise(txt)))


def _walk_for_trigger_keys(node: object) -> bool:
    """A trigger key must appear as an actual mapping KEY, at any nesting depth.

    Iterative with a visited set, for the same reason as `_substantive` and with the
    same history one round compressed: a depth cap of 40 with branching factor 2 is
    ~2^40 visits, so a 20-byte `a: &a\\n b: *a\\n c: *a\\n` hung the gate with no
    output, no exit and no traceback — and `--survey` died with it, since a loop that
    never raises is not catchable by its per-skill `except Exception`. Step 5 runs for
    EVERY skill at every tier, which made this the widest-reaching instance.

    The cap is gone rather than paired with a memo: the two together made the answer
    depend on which branch was walked first (round 18). One visit per distinct node
    bounds the work without making the verdict a function of the traversal.
    """
    seen: set[int] = set()
    stack = [node]
    while stack:
        cur = stack.pop()
        if id(cur) in seen:
            continue
        seen.add(id(cur))
        if isinstance(cur, dict):
            if TRIGGER_ASSERTION_KEYS & set(map(str, cur.keys())):
                return True
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return False


def _syntax_checkable(path: Path) -> bool:
    """Whether this build can actually syntax-check the file. Used so the PASS line
    never claims `syntax ok` about something nothing examined."""
    if _ext(path) in (".py", ".sh"):
        return True
    if _ext(path) in (".mjs", ".js", ".ts"):
        return bool(shutil.which("node"))
    if not _ext(path):
        head = (_read(path) or "").splitlines()[:1]
        m = _SHEBANG_RE.match(head[0]) if head else None
        if not m:
            return False
        i = m.group(1).lower()
        return (i in _SH_INTERPRETERS or i in _PY_INTERPRETERS
                or (i in _NODE_INTERPRETERS and bool(shutil.which("node"))))
    return False


def _script_syntax_error(path: Path) -> str | None:
    """Return an error string if the script has a syntax error, else None.
    .mjs/.js/.ts checked only when `node` is present; otherwise not blocked."""
    if _ext(path) == ".py":
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError:
            return "python syntax error"
        return None
    if _ext(path) == ".sh":
        r = subprocess.run(["bash", "-n", str(path)], capture_output=True)
        return None if r.returncode == 0 else "shell syntax error"
    if _ext(path) in (".mjs", ".js", ".ts") and shutil.which("node"):
        r = subprocess.run(["node", "--check", str(path)], capture_output=True)
        return None if r.returncode == 0 else "node syntax error"
    if not _ext(path):
        return _shebang_syntax_error(path)
    return None


_SHEBANG_RE = re.compile(r"^#!\s*(?:\S*/)?(?:env\s+)?([\w.-]+)")
# Word-boundary interpreter names. `"sh" in shebang` substring-matched `fish` and
# `zsh`, running `bash -n` over a fish script and reporting a false syntax error.
_SH_INTERPRETERS = {"sh", "bash", "dash", "ksh"}
_PY_INTERPRETERS = {"python", "python2", "python3"}
_NODE_INTERPRETERS = {"node", "nodejs"}


def _shebang_syntax_error(path: Path) -> str | None:
    """Syntax-check an extensionless executable by its shebang.

    Counting a file as code without checking it was worse than not counting it: the
    gate printed `syntax ok` about a file whose syntax was never examined. Anything
    with an interpreter we cannot check returns the SKIPPED sentinel so the caller
    does not claim otherwise.
    """
    head = (_read(path) or "").splitlines()[:1]
    if not head:
        return None
    m = _SHEBANG_RE.match(head[0])
    if not m:
        return None
    interp = m.group(1).lower()
    if interp in _SH_INTERPRETERS:
        r = subprocess.run(["bash", "-n", str(path)], capture_output=True)
        return None if r.returncode == 0 else "shell syntax error"
    if interp in _PY_INTERPRETERS:
        try:
            _ast_parse(_read(path) or "")
        except SyntaxError:
            return "python syntax error"
        return None
    if interp in _NODE_INTERPRETERS and shutil.which("node"):
        r = subprocess.run(["node", "--check", str(path)], capture_output=True)
        return None if r.returncode == 0 else "node syntax error"
    return None


# --- internal-reference integrity (step 1c) ----------------------------------
# A skill must not advertise files it doesn't ship. This is the #1 real defect
# (a SKILL.md "Script: scripts/x.py" / "see references/y.md" for a file that does
# not exist). We check the skill's OWN structured subdirs (scripts/ references/
# assets/ templates/) — the high-signal, low-false-positive surface — and only in
# PROSE: fenced code blocks (example commands + File-Structure trees) are stripped
# first. A reference is satisfied if the file exists in the skill, ships as a
# scaffold-template output under assets/templates/ (skills that WRITE files into a
# target repo), or sits on a line marked Planned / not-yet / generated / etc.
_REF_RE = re.compile(
    r"(?<![\w./-])((?:scripts|references|assets|templates)/[A-Za-z0-9_][\w./-]*\.[A-Za-z0-9]+)"
)
# Explicit planning language only — deliberately NOT common bare English words
# ("generated"/"will be"/"deprecated"/"stub"), which could incidentally exempt a
# genuinely-missing live reference (P20 review). The exemption is line-level, so
# keep these unambiguous.
_PLANNED_RE = re.compile(
    r"planned|not[\s-]?yet|not[\s-]?shipped|not[\s-]?(?:yet[\s-]?)?(?:built|implemented|written|created)"
    r"|roadmap|do(?:n['’]t| not)\s+invoke|\bTODO\b|\bTBD\b|coming soon|placeholder",
    re.IGNORECASE,
)
_SKIP_JSON_KEYS = {"description", "summary", "notes", "when_to_use", "trigger", "triggers"}


def _strip_fences(md: str) -> str:
    """Drop fenced code blocks — example commands and File-Structure trees inside them
    are not live contract claims.

    Handles the four forms that reached an earlier draft as live text: ``` fences,
    ~~~ fences, an UNTERMINATED fence (everything after it is example, not record),
    and HTML comments. Four-space-indented blocks are handled by the caller where it
    matters, since stripping them globally would eat ordinary nested list prose.
    """
    md = re.sub(r"<!--.*?-->", "", md, flags=re.DOTALL)
    md = re.sub(r"(?m)^[ \t]*(```|~~~).*?^[ \t]*\1[^\n]*$", "", md, flags=re.DOTALL)
    # Unterminated forms last, and after closed fences are gone — running the greedy
    # HTML-comment strip first meant a bare `<!--` inside a fenced EXAMPLE deleted
    # every real entry below it.
    md = re.sub(r"(?ms)^[ \t]*(?:```|~~~).*\Z", "", md)
    md = re.sub(r"(?s)<!--.*\Z", "", md)
    return md


def _ref_satisfied(skill_dir: Path, ref: str) -> bool:
    ref = ref.lstrip("./")
    if (skill_dir / ref).exists():
        return True
    # scaffold-template output: a skill that writes files into a TARGET repo ships
    # them under assets/templates/ (e.g. harness-engineering-playbook).
    if (skill_dir / "assets" / "templates" / ref).exists():
        return True
    leaf = ref.split("/", 1)[1] if "/" in ref else ref
    return (skill_dir / "assets" / "templates" / leaf).exists()


def _internal_ref_issues(skill_dir: Path) -> list[str]:
    """List references (SKILL.md prose / skill.json / templates/*.yaml) that point
    at skill-internal files which do not exist and are not marked planned."""
    issues: list[str] = []
    md = skill_dir / "SKILL.md"
    if md.is_file():
        raw_md = _read(md)
        if raw_md is None:
            issues.append("SKILL.md is unreadable — references cannot be verified")
            raw_md = ""
        body = _strip_fences(raw_md)
        for ln in body.splitlines():
            planned = bool(_PLANNED_RE.search(ln))
            for m in _REF_RE.finditer(ln):
                ref = m.group(1)
                if not planned and not _ref_satisfied(skill_dir, ref):
                    issues.append(f"SKILL.md → {ref} (missing; not marked planned)")
    sj = skill_dir / "skill.json"
    if sj.is_file():
        try:
            data = _json_loads(sj.read_text(encoding="utf-8", errors="replace"))
        except _DuplicateKey as e:
            # Must be REPORTED, not swallowed. The first version of this fix added the
            # hook and left the `except ValueError` below to catch it, so the duplicate
            # was detected and then discarded into `data = None` — which skips the
            # entrypoint check entirely and PASSES. Detecting a defect and then
            # dropping it is worse than not detecting it: the gate now has evidence it
            # is ignoring.
            data = None
            issues.append(f"skill.json declares {e.key!r} twice — last-wins would "
                          "decide which reference this skill advertises")
        # RecursionError is NOT a ValueError, so a deeply nested skill.json crashed the
        # run with a bare traceback. Third sibling site of the same class: round 13
        # capped `_substantive` and left `_load_data`'s json arm and this one uncovered.
        except (ValueError, OSError, RecursionError):
            data = None
        ep = data.get("entrypoint") if isinstance(data, dict) else None
        if isinstance(ep, str) and ep and not _ref_satisfied(skill_dir, ep):
            issues.append(f"skill.json entrypoint → {ep} (missing)")

        def _walk(o, key="", depth=0):
            if depth > _MAX_NESTING:
                return  # same cap, same reason: report, never throw
            if isinstance(o, str):
                if key in _SKIP_JSON_KEYS or key == "entrypoint":
                    return  # entrypoint already checked explicitly above (no double-count)
                for m in _REF_RE.finditer(o):
                    ref = m.group(1)
                    if not _ref_satisfied(skill_dir, ref):
                        issues.append(f"skill.json → {ref} (missing)")
            elif isinstance(o, dict):
                for k, v in o.items():
                    _walk(v, k, depth + 1)
            elif isinstance(o, list):
                for v in o:
                    _walk(v, key, depth + 1)
        _walk(data)
    tdir = skill_dir / "templates"
    if tdir.is_dir():
        for y in sorted([*tdir.rglob("*.yaml"), *tdir.rglob("*.yml")]):
            raw_y = _read(y)
            if raw_y is None:
                issues.append(f"{y.relative_to(skill_dir)} is unreadable — "
                              "references cannot be verified")
                raw_y = ""
            for ln in raw_y.splitlines():
                planned = bool(_PLANNED_RE.search(ln))
                for m in _REF_RE.finditer(ln):  # all 4 subdir prefixes, not just scripts/
                    ref = m.group(1)
                    if not planned and not _ref_satisfied(skill_dir, ref):
                        issues.append(f"{y.relative_to(skill_dir)} → {ref} (missing)")
    seen, out = set(), []
    for i in issues:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


# --- tiers (D / J / L) -------------------------------------------------------
#
# The gate used to ask "is there a deterministic core?" and treat *no* as either a
# failure or, with `latent_only: true`, a total exemption. That made a testability
# question decide an expressibility question: a judgment skill (`critique`) and a
# lens (`look-back`) have no pure function and are unambiguously skills. Worse, the
# exemption branch gated NOTHING — the accommodation was an amnesty.
#
# Three tiers replace the binary. Each names what the skill IS and therefore which
# gate applies. Inference decides *which* gate, never *whether* one applies: a skill
# the gate cannot classify still fails.
#
# EVERY check below is content-based, not presence-based. A gate whose artifacts can
# be satisfied by `touch` is the vacuous pass this file spends 20 lines warning about
# at the step-5 comment; two adversarial reviews found nine ways to `touch` an earlier
# draft of this block into a PASS.
TIER_D, TIER_J, TIER_L = "D", "J", "L"
TIERS = (TIER_D, TIER_J, TIER_L)

# Model families, for the cross-model-judge check. A judge sharing the generator's
# substrate inflates confidence rather than testing it, so J requires the judge model
# to differ from the model under eval. Exact inequality is REQUIRED; same-family is a
# WARN — detecting true cross-vendor from a bare string is not something this gate can
# do honestly, and pretending otherwise would be the vacuity it exists to prevent.
_MODEL_FAMILIES = {
    "anthropic": ("claude", "opus", "sonnet", "haiku", "fable"),
    "openai": ("gpt", "o1", "o3", "o4", "codex"),
    "google": ("gemini", "palm"),
    "meta": ("llama",),
    "mistral": ("mistral", "mixtral"),
}

# Content that is a promise rather than a record. Accepting any of these as a rubric,
# a method or a measured value is how "declare a floor AND show the measurement"
# degrades into "type something in the field".
# Anchored matching missed "TBD later" and "vibes only", so this scans for the marker
# ANYWHERE in the value. Deliberately a typo-catcher, NOT an authenticity gate — see
# the "what this cannot check" note in SKILL.md. No regex can tell whether 40 cases
# were really labelled; that is what the P20 review layer is for.
def _model_family(model: str) -> str | None:
    m = (model or "").lower()
    for fam, toks in _MODEL_FAMILIES.items():
        if any(t in m for t in toks):
            return fam
    return None


def _is_num(x: object) -> bool:
    """A finite real number. `bool` is an int in Python and must not qualify as a
    score, and NaN/inf are floats that are not coefficients — `agreement_floor: NaN`
    satisfied a bare isinstance check."""
    return (isinstance(x, (int, float)) and not isinstance(x, bool)
            and math.isfinite(x))


def _fm(fm: dict | None, key: str, default: object = None) -> object:
    """Read a frontmatter key case-INSENSITIVELY. Every gate-affecting read goes here.

    `_count_top_level_key` has always lowercased the key it counts, and
    `_admission_issue` was fixed early to match — its comment names the reason: reading
    `Outcome: admitted` as "declares no outcome" is "an undocumented asymmetry that
    reads as the gate not seeing what is plainly there."

    `_tier_of` was never given the same treatment, and the asymmetry there is a false
    ACCEPT rather than a false reject. Measured:

        Tier: J   + scripts, no J core  ->  PASS "tier D (inferred: ships scripts/ code)"
        tier: J   + scripts, no J core  ->  FAIL "tier J (declared): 4 gap(s)…"

    One capital letter and a declared tier-J skill passes on scripts alone, with the
    admission record, rubric, held-out cases and judge config never consulted — the
    exact sentence the duplicate-`tier:` fix was written to close.

    Fixing `tier` alone would have been the SIXTH one-site fix in this arc for a class
    with several sites, so this is the accessor and there are no per-key exceptions:
    the property is "frontmatter keys are matched case-insensitively", full stop.
    """
    if not fm:
        return default
    want = key.strip().lower()
    for k, v in fm.items():
        if str(k).strip().lower() == want:
            return v
    return default


def _duplicate_top_level_key_issue(path: Path) -> str | None:
    """ANY top-level frontmatter key declared twice is ambiguous. Not just `tier:`.

    YAML resolves duplicate keys last-wins, silently, so a declaration a reader sees
    on line 4 is not necessarily the one that governs. Measured on this gate, before
    the check existed:

      * `tier: J` then `tier: D` -> reported "tier D (declared)" and PASSED on
        scripts+tests alone; admission record, rubric, held-out cases and judge config
        never consulted.
      * `latent_only: true` then `latent_only: false` -> PASSED, escaping a REQUIRED
        FAIL whose control ("latent_only:true but 1 script(s) present — contradiction")
        fires on the single-key version.
      * `name:` and `description:` twice -> identity and the routing surface silently
        become the last one.

    The first version of this check took a `key` argument and was pointed at `tier`
    alone, which made it the FOURTH one-site fix for a several-site class in this arc
    (three near-copies of the frontmatter regex; `outcome:` but not `tier:`; the
    opening fence but not the closing one). Keying it to a list would have been the
    fifth: the property is "declare each key once", not "declare these keys once", and
    a future gate-deciding key should be covered the day it is added rather than the
    day someone remembers to enumerate it.

    Measured over all 96 SKILL.md in this repo: 0 have duplicate top-level keys, 0 are
    unparseable, 0 lack a matched frontmatter block. The blanket rule costs nothing on
    the real population.

    Returns None only when there is genuinely no parser installed. A block a parser
    REJECTS is a reported defect, not a residue — that conflation was the round-13
    blocker, and the round-13 fix then keyed the refusal on `yaml.compose` raising,
    which is not the condition that triggers the fallback scanner. Round 14 found the
    gap with a YAML tag: composes fine, `safe_load` raises. The refusal now keys on
    `parse_frontmatter_status(...) == FM_FALLBACK`.

    The no-parser residue stays deliberate: answering the duplicate question without a
    YAML parser means rebuilding the line-based key walker this file deleted twice, for
    the same reason both times.
    """
    raw = _read(path)
    if raw is None:
        return None
    m = _frontmatter_match(raw)
    if m is None:
        return None
    disagreement = _frontmatter_disagreement_issue(path, "SKILL.md frontmatter")
    if disagreement:
        return disagreement
    # No `unparseable` branch here any more. `compose` is a strict prefix of the work
    # `safe_load` does, so a block compose rejects is one safe_load also rejects — which
    # `_frontmatter_disagreement_issue` above has already refused. Mutant M76 SURVIVED
    # against that shadowed branch, which is this file's own standard for deleting it:
    # a mutant that cannot die is dishonest bookkeeping, not coverage.
    status, dupes = _duplicate_top_level_keys(m.group(1))
    if status != "ok" or not dupes:
        return None
    shown = ", ".join(f"`{k}:` x{n}" for k, n in dupes)
    return (f"SKILL.md frontmatter declares the same key twice ({shown}) — YAML resolves "
            "duplicates last-wins, so the value that governs is not the first one a "
            "reader sees; declare each key once")


def _substantive_leaf(x: object) -> bool:
    """Is this SCALAR a value? Split out so the container walk and the leaf rule cannot
    drift apart, and so the walk below can stay a plain reachability question."""
    if isinstance(x, bool):
        return False
    if isinstance(x, (int, float)):
        return math.isfinite(x)
    return isinstance(x, str) and bool(x.strip())


def _substantive(x: object) -> bool:
    """Structural presence: a finite number, a non-empty string, or a container that
    reaches at least one of those.

    This used to try to detect placeholder CONTENT — "TBD", "vibes", "n/a" — and was
    rebuilt five times, each rebuild producing fresh FALSE REJECTS on honest prose
    ("Write me a concise incident report from these logs.", "excluded 3 cases with
    unknown labels"). That question is undecidable and SKILL.md declares it out of
    scope. What is left is reachability: is there a value in here at all.

    ITERATIVE, with a visited set, and NO depth cap. Three attempts preceded that:

      * round 11 — recursion + a PATH-based `_seen` frozenset. Stops cycles only;
        because each sibling gets its own copy, a node reachable by many paths is
        walked once per path, so an ACYCLIC alias DAG (876 bytes) hung it.
      * round 13 — added `_MAX_NESTING` after a 1.4 KB `evals/suite.json` nested ~500
        deep raised RecursionError out of `run_checklist`: a bare traceback where this
        file's contract says report, never throw.
      * round 17 — swapped the path-set for a memo, which fixed the DAG but made the
        answer ORDER-DEPENDENT, because the cap was evaluated before the memo. A node
        whose subtree the cap truncated cached that `False` and returned it later at a
        shallower depth where the whole subtree was in budget. Measured: a 584-byte
        valid tier-L artifact flipped a required gate PASS -> FAIL depending only on
        which branch was walked first.

    A depth cap and a memo cannot coexist honestly: the cap makes the answer a function
    of the budget, and the memo caches it as if it were a function of the node. An
    explicit stack removes the reason for the cap (there is no Python recursion to
    overflow) and the visited set bounds the work at one visit per distinct node, so
    cycles, DAGs and 20000-deep nesting all terminate and the answer depends only on
    the data.
    """
    if not isinstance(x, (dict, list, tuple, set)):
        return _substantive_leaf(x)
    seen: set[int] = set()
    stack = [x]
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, (list, tuple, set)):
            stack.extend(node)
        elif _substantive_leaf(node):
            return True
    return False


def _read(path: Path) -> str | None:
    """Read text, or None if unreadable. Every caller must fail CLOSED on None — an
    unreadable artifact is an unverified artifact, never a traceback."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


class _Unparseable:
    """Sentinel: the file exists but the gate cannot trust what it says. Distinct from
    'absent', so the gate can say which — reporting a correct YAML judge config as
    `no judge config` was a real misdiagnosis in review.

    `reason` exists because "cannot verify" now covers more than "no pyyaml": a
    duplicate key that last-wins would silently decide, and a document nested too
    deeply to parse. Telling an author "could not be parsed" when the real defect is a
    duplicated `execution_contract:` is the same misdiagnosis one level down.
    """
    __slots__ = ("path", "reason")

    def __init__(self, path: Path, reason: str | None = None):
        self.path = path
        self.reason = reason


class _DuplicateKey(ValueError):
    """Raised by the JSON object-pairs hook. Subclasses ValueError deliberately: any
    caller that already treats malformed JSON as unverifiable keeps doing the right
    thing if it does not know about this."""

    def __init__(self, key: str):
        super().__init__(f"duplicate key {key!r}")
        self.key = key


def _no_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict:
    seen: set[str] = set()
    for k, _ in pairs:
        if k in seen:
            raise _DuplicateKey(k)
        seen.add(k)
    return dict(pairs)


def _duplicate_key_in_node(text: str) -> str | None:
    """First duplicate key ANYWHERE in a YAML document, via the node tree.

    `safe_load` has already collapsed duplicates by the time it returns, so this walks
    `compose()` — the same parser-answers-the-parser's-question move the SKILL.md check
    makes. Nested, not just top-level: `judge:` and `execution_contract:` are found by
    `_dig_all` at any depth, so a duplicate at any depth decides a gate.
    """
    # No `yaml is None` guard: `_load_data` returns `_Unparseable` before calling this
    # when there is no parser, so such a branch could never execute. Round 15 deleted
    # two mutants for naming unreachable branches and then added one; not twice.
    try:
        root = yaml.compose(text)
    except Exception:
        return None  # the caller has already reported it as unparseable

    # `visited` is the cycle guard, and its absence was the worst defect of this arc.
    # A recursive anchor —
    #
    #     cases: &x
    #       nested: *x
    #
    # — is a document `safe_load` ACCEPTS (PyYAML builds a self-referential dict), and
    # this walk popped the same MappingNode and pushed it back forever: no output, no
    # exit, no traceback. `--survey` hung with it, and `survey()`'s per-skill
    # `except Exception` cannot catch a non-terminating loop. `_substantive` twelve
    # lines up has carried exactly this guard since round 11 and it was not carried
    # over — a fail-closed gate turned into a silent one, which is strictly worse than
    # the last-wins bypass this function was added to close.
    #
    # Visiting each node once is also correct for the question being asked: duplicates
    # are a property of a single mapping, so a shared (aliased) subtree needs one visit.
    visited: set[int] = set()
    stack = [root]
    while stack:
        node = stack.pop()
        if id(node) in visited:
            continue
        visited.add(id(node))
        if isinstance(node, getattr(yaml, "MappingNode", ())):
            seen: set[str] = set()
            for k, v in node.value:
                name = str(getattr(k, "value", ""))
                # No `<<` carve-out. Round 16 added one, justified in a comment
                # claiming PyYAML merges repeated merge keys "left to right, first wins
                # per key, so it is NOT last-wins". Measured on PyYAML 6.0.3, that is
                # exactly inverted:
                #
                #     a: &A {k: FROM_A}
                #     b: &B {k: FROM_B}
                #     m: {<<: *A, <<: *B}   ->  {'k': 'FROM_B'}
                #     n: {<<: *B, <<: *A}   ->  {'k': 'FROM_A'}
                #
                # Repeated `<<` IS last-wins, so it is precisely the ambiguity this
                # function exists to refuse — and the carve-out let swapping two
                # adjacent lines flip a REQUIRED tier-J gate from FAIL to PASS on a
                # self-judging judge declaration. The property was asserted in prose
                # without being run; the refusal was right all along.
                if name in seen:
                    return name
                seen.add(name)
                stack.append(v)
        elif isinstance(node, getattr(yaml, "SequenceNode", ())):
            stack.extend(node.value)
    return None


def _load_data(path: Path) -> object | None | _Unparseable:
    """Parse a JSON/YAML artifact. None = absent/empty; _Unparseable = cannot verify."""
    txt = _read(path)
    if txt is None:
        return _Unparseable(path)  # unreadable is UNVERIFIED, not absent
    if not txt.strip():
        return None
    # Duplicate top-level keys are resolved last-wins, silently, by BOTH parsers.
    # `SKILL.md` has been guarded against that three times in this arc; `evals/*` — the
    # documents carrying tier J's entire contract — never were, which made this the
    # seventh instance of the same class. Measured: a duplicated `execution_contract:`
    # hid a self-judging declaration and the gate printed "cross-model judge with a
    # measured floor"; a duplicated `judge:` defeated "declare exactly one", a rule the
    # same gate enforces correctly ACROSS files while key order inside one file decided
    # it. `_dig_all`'s docstring already says filename order is not a security boundary;
    # neither is key order.
    if _ext(path) == ".json":
        try:
            return _json_loads(txt)
        except _DuplicateKey as e:
            return _Unparseable(path, f"duplicate key {e.key!r} — last-wins would decide it")
        except RecursionError:
            # json.loads recurses; `except ValueError` never caught this, so a deeply
            # nested artifact crashed the whole run with a bare traceback. The yaml arm
            # below always caught it via `except Exception`, and `_is_trigger_eval`
            # guards it explicitly — the guard existed at the LATER site, not this one.
            return _Unparseable(path, "nested too deeply to parse")
        except ValueError:
            return _Unparseable(path)
    if _ext(path) in {".yaml", ".yml"}:
        if yaml is None:
            return _Unparseable(path)
        try:
            data = yaml.safe_load(txt)
        except Exception:
            return _Unparseable(path)
        dup = _duplicate_key_in_node(txt)
        if dup:
            return _Unparseable(path, f"duplicate key {dup!r} — last-wins would decide it")
        return data
    return None


def _unparseable_detail(u: "_Unparseable") -> str:
    """`name — why`. The reason is the point: "could not be parsed" sent an author
    hunting for a syntax error when the actual defect was a duplicated key that
    last-wins would have decided silently."""
    if u.reason:
        return f"{u.path.name} — {u.reason}"
    hint = "fix the file" if _ext(u.path) == ".json" else "install pyyaml or fix the file"
    return f"{u.path.name} — {hint}"


def _eval_blobs(skill_dir: Path) -> tuple[list[tuple[Path, dict]], list[_Unparseable]]:
    """Every parseable mapping under evals/, plus the files that could not be parsed.

    The unparseable list is returned rather than swallowed: a J skill whose judge
    config is a YAML file this build cannot read must FAIL saying so, not FAIL saying
    the config is missing, and must never PASS by the file being invisible.
    """
    out: list[tuple[Path, dict]] = []
    bad: list[_Unparseable] = []
    d = skill_dir / "evals"
    if not d.is_dir():
        return out, bad
    for f in sorted(d.rglob("*")):
        if not f.is_file() or _ext(f) not in {".json", ".yaml", ".yml"}:
            continue
        data = _load_data(f)
        if isinstance(data, _Unparseable):
            bad.append(data)   # the sentinel, not the Path: it carries WHY
        elif isinstance(data, dict):
            out.append((f, data))
        elif isinstance(data, list):
            # A top-level list is an ordinary prompt set. Keeping only dicts made it
            # INVISIBLE, so the gate reported "no routing eval" about a file that was
            # present and well-formed. Wrap it so polarity can still be read.
            out.append((f, {"cases": data}))
    return out, bad


def _dig_all(blobs: list[tuple[Path, dict]], key: str) -> list[tuple[Path, object]]:
    """EVERY top-level value for `key`, with its file.

    Deliberately not first-match-wins. A first-match `_dig` let `evals/aaa-decoy.yaml`
    supply the `judge` while `evals/zzz-real.yaml` supplied the `execution_contract`,
    so the gate compared two configs that never meet at runtime and called a
    self-judging setup cross-model. Filename order is not a security boundary.
    """
    return [(f, data[key]) for f, data in blobs if key in data]


_ADMISSION_TEMPLATE = (
    "  (at the very top of the file, before anything else)\n"
    "  ---\n  outcome: admitted   # or: rejected\n  ---\n\n"
    "  <what two agents were given, and what the third party judged>\n")


def _admission_issue(skill_dir: Path) -> str | None:
    """Tier J's hard gate, read from a DECLARED field rather than from prose.

    `evals/admission.md` must open with YAML frontmatter carrying `outcome: admitted`
    (or `rejected`). The admission test itself — given the same input, can two
    independent agents produce outputs a competent third party judges BOTH valid? — is
    written in the body, for a human to read.

    Earlier versions scanned the prose for the verdict and were rebuilt four times.
    Each rebuild false-rejected honest records: "Neither candidate was rejected by the
    judge.", "Outcome: admitted — both outputs were judged valid; neither was
    rejected.", a markdown table of results, a record quoting another skill's rejected
    outcome, a backticked `admitted`, a body opening "The planned protocol was
    completed". Natural language has no reliable surface for this, and a gate that
    guesses at it teaches people to write for the regex instead of for the reader.

    A declared field is decidable, states the contract plainly, and cannot be
    misparsed. It does not prove the test happened — nothing static can, and SKILL.md
    says so — but it makes the author's own verdict unambiguous.
    """
    if yaml is None:
        return ("tier J's admission record is a YAML contract and this build has no "
                "yaml module — `pip install pyyaml`; the gate will not pass frontmatter "
                "it cannot parse")
    f = skill_dir / "evals" / "admission.md"
    if not f.is_file():
        return ("no evals/admission.md — record the admission test and declare its "
                f"outcome in frontmatter:\n{_ADMISSION_TEMPLATE}")
    # The same two-readers-disagree class as the tier site. `outcome:` is read through
    # parse_frontmatter, so a block YAML rejects lets the scanner's last-wins value
    # stand: a declared `outcome: rejected` was reported as admitted.
    disagreement = _frontmatter_disagreement_issue(f, "evals/admission.md frontmatter")
    if disagreement:
        return disagreement
    raw = _read(f)
    if raw is None:
        return "evals/admission.md is unreadable"
    m = _frontmatter_match(raw)
    if m is None:
        return ("evals/admission.md has no frontmatter block — add:\n"
                f"{_ADMISSION_TEMPLATE}")
    fm = parse_frontmatter(f) or {}
    # Case-insensitive KEY lookup: the value was already compared case-insensitively,
    # so `Outcome: admitted` failing with "declares no outcome" was an undocumented
    # asymmetry that reads as the gate not seeing what is plainly there.
    present = [v for k, v in fm.items() if str(k).strip().lower() == "outcome"]
    outcome = str(present[0]).strip().lower() if present else ""
    if present and outcome in ("", "none", "null"):
        return ("evals/admission.md declares an empty `outcome` — set it to `admitted` "
                "or `rejected`")
    if not outcome:
        return ("evals/admission.md declares no `outcome` in frontmatter — add:\n"
                f"{_ADMISSION_TEMPLATE}")
    if outcome not in ("admitted", "rejected"):
        return f"evals/admission.md outcome: {outcome!r} — must be `admitted` or `rejected`"
    if outcome == "rejected":
        return ("evals/admission.md declares `outcome: rejected` — an underspecified "
                "skill is not admissible")
    # A block that does not parse as a YAML mapping is malformed frontmatter — which
    # is also how `---xyz` (a fence the matcher ran past) surfaces, without a
    # hand-rolled `---`-in-block rule that false-rejected `---source: author-record`.
    # `declared is None` is unreachable now: no parser is refused at the top of this
    # function, and a block compose rejects is refused by the disagreement check above.
    # Mutant M65 SURVIVED against it. Deleted rather than kept as an unkillable guard.
    declared = _count_top_level_key(m.group(1), "outcome")
    if declared is not None and declared > 1:
        return (f"evals/admission.md declares `outcome` {declared} times — "
                "contradictory declarations; keep exactly one")
    body = raw[m.end():]
    if not body.strip():
        return ("evals/admission.md declares an outcome but records nothing — write "
                "what two agents were given and what a third party judged")
    return None


def _rubric_issue(skill_dir: Path, blobs: list[tuple[Path, dict]]) -> str | None:
    """A rubric names the dimensions a third party grades on. An EMPTY rubric.md
    satisfied an earlier draft — the same presence-is-not-correctness trap step 3
    already avoids via _is_real_test."""
    for _, val in _dig_all(blobs, "rubric"):
        if isinstance(val, dict):
            if any(_substantive(k) and _substantive(v) for k, v in val.items()):
                return None
            continue
        if isinstance(val, list):
            if any(_substantive(v) for v in val):
                return None
            continue
        if _substantive(val):
            return None
    f = skill_dir / "evals" / "rubric.md"
    if not f.is_file():
        return "no rubric (evals/rubric.md or a `rubric` key in evals/)"
    txt = _read(f)
    if txt is None:
        return "evals/rubric.md is unreadable"
    body = [ln.strip() for ln in _strip_fences(txt).splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    if not body:
        return "evals/rubric.md has no content below its heading — an empty rubric grades nothing"
    return None


_CASE_EXTS = {".json", ".yaml", ".yml", ".md", ".txt", ".jsonl"}


def _held_out_count(skill_dir: Path, blobs: list[tuple[Path, dict]]) -> int:
    """Held-out cases: a dedicated evals/held-out/ dir, or cases flagged held_out.

    Counts CASES, not files. `.gitkeep`, `README.md` and dotfiles are not cases, and
    an empty file is not a case — `touch evals/held-out/.gitkeep` satisfied an earlier
    draft's "held-out case set".
    """
    n = 0
    d = skill_dir / "evals" / "held-out"
    if d.is_dir():
        for f in d.rglob("*"):
            if not f.is_file() or f.name.startswith(".") or _ext(f) not in _CASE_EXTS:
                continue
            if f.stem.lower() in {"readme", "index", "template", "example"}:
                continue
            txt = _read(f)
            if _substantive(txt):
                n += 1
    for _, data in blobs:
        cases = data.get("cases")
        if isinstance(cases, list):
            n += sum(1 for c in cases if isinstance(c, dict)
                     and str(c.get("held_out", "")).lower() in ("true", "yes", "1")
                     # a case needs an actual input; `{"held_out": true}` alone is a
                     # marker object, not a held-out case
                     and any(_substantive(c.get(k)) for k in ("prompt", "input", "case", "text")))
    return n


def _judge_issues(blobs: list[tuple[Path, dict]]) -> tuple[list[str], list[str]]:
    """Validate tier J's judge declaration. Returns (failures, warnings).

    Required: exactly one well-formed `judge` mapping with a `model`; at least one
    `execution_contract.model` to compare it against (the comparison target is NOT
    optional — omitting it used to degrade the whole cross-model requirement to a
    WARN, making it opt-out); the judge model must differ from EVERY declared
    model-under-eval; and an `agreement_floor` that is a real number accompanied by an
    `agreement_measured` record carrying a substantive value and method.

    The floor's VALUE is deliberately unconstrained. Nobody has measured what it should
    be, and hard-coding one would assert a number no committed process regenerates —
    the exact failure that produced this tier model. The gate enforces the shape:
    declare a floor, and show the measurement that produced it.
    """
    fails: list[str] = []
    warns: list[str] = []

    judges = _dig_all(blobs, "judge")
    if not judges:
        return ["no `judge` config in evals/ (tier J needs a cross-model judge declaration)"], warns
    # EVERY declaration counts toward ambiguity, well-formed or not. Skipping the
    # malformed ones meant a decoy {"judge": "not-a-mapping"} was simply ignored, so
    # "declare exactly one" was not actually enforced.
    if len(judges) > 1:
        names = ", ".join(f.name for f, _ in judges)
        return [f"{len(judges)} `judge` declarations ({names}) — ambiguous; declare exactly one"], warns
    if not isinstance(judges[0][1], dict):
        return [f"`judge` in {judges[0][0].name} is {type(judges[0][1]).__name__}, not a mapping"], warns
    judge = judges[0][1]

    jm = judge.get("model")
    if not (isinstance(jm, str) and jm.strip()):
        fails.append("judge.model missing or not a string")
        jm = ""

    unders = []
    for f, ec in _dig_all(blobs, "execution_contract"):
        if not isinstance(ec, dict):
            fails.append(f"execution_contract in {f.name} is {type(ec).__name__}, not a mapping")
            continue
        m = ec.get("model")
        if m is None:
            continue
        if not (isinstance(m, str) and m.strip()):
            fails.append(f"execution_contract.model in {f.name} is {m!r} — must be a "
                         "non-empty string or absent")
            continue
        unders.append(m.strip())
    if jm and not unders:
        fails.append("no execution_contract.model in evals/ — nothing to compare judge.model "
                     "against, so cross-model distinctness cannot be established")
    elif jm:
        same = [u for u in unders if u.lower() == jm.strip().lower()]
        if same:
            fails.append(f"judge.model == a model under eval ({jm!r}) — self-judging is not a gate")
        else:
            fam = [u for u in unders if _model_family(jm) and _model_family(jm) == _model_family(u)]
            if fam:
                warns.append(f"judge.model {jm!r} and model-under-eval {fam[0]!r} share a family "
                             f"({_model_family(jm)}) — distinct names, correlated substrate")

    floor = judge.get("agreement_floor")
    measured = judge.get("agreement_measured")
    if floor is None:
        fails.append("judge.agreement_floor not declared")
    elif not _is_num(floor):
        fails.append(f"judge.agreement_floor is {floor!r} — must be a number")
    elif not isinstance(measured, dict):
        fails.append(f"judge.agreement_floor={floor} declared with no agreement_measured "
                     "{value, method} — an unmeasured floor is an authored number")
    elif not _substantive(measured.get("value")) or not _substantive(measured.get("method")):
        fails.append("judge.agreement_measured is missing a value or a method "
                     f"(value={measured.get('value')!r}, method={measured.get('method')!r}) — "
                     "both must be present and non-empty")
    return fails, warns


_POSITIVE_KEYS = {"should_trigger", "shouldTrigger", "should_fire"}
# `shouldNotTrigger` was missing while `shouldTrigger` was present, so a camelCase
# routing eval was FALSE-REJECTED for "asserts only one polarity" while step 5 called
# the same file a valid trigger eval — the self-contradiction `_blob_polarity`'s
# docstring warns about. One accommodation added at one of its two sites.
_NEGATIVE_KEYS = {"should_not_trigger", "shouldNotTrigger", "should_not_fire",
                  "negative_case"}


def _case_polarity(case: object) -> tuple[bool, bool]:
    """(positive, negative) for ONE case in the per-case boolean shape."""
    pos = neg = False
    if isinstance(case, dict):
        for k, v in case.items():
            ks = str(k)
            if ks in _POSITIVE_KEYS and isinstance(v, bool):
                pos, neg = (pos or v), (neg or not v)
            elif ks in _NEGATIVE_KEYS and isinstance(v, bool):
                neg = neg or v
    return pos, neg


def _blob_polarity(data: dict) -> tuple[bool, bool]:
    """(positive, negative) for one eval document, across BOTH shapes in use here.

    Shape A — role-x resolver evals, the only routing-eval format this repo actually
    ships (14 files under roles/): top-level `should_fire:` / `should_not_fire:` each
    mapping to a LIST of prompts. An earlier draft required booleans and would have
    rejected every one of them — while step 5 reported the same file as a valid
    trigger eval, the gate contradicting itself about one file. Tier L was proven
    only against a fixture shape that existed nowhere but its own tests.

    Shape B — Schmid prompt sets: a `cases` list whose entries carry boolean
    `should_trigger` / `should_fire` / `should_not_fire`.

    In shape B the two polarities must come from DIFFERENT cases. One case asserting
    `should_fire: true` AND `should_not_fire: true` is self-contradictory and used to
    satisfy "both polarities" on its own.
    """
    pos = neg = False
    for k, v in data.items():
        # `_substantive`, not just `and v`. This was the one tier-artifact check
        # without a substance floor while all three siblings carry one
        # (`_rubric_issue`, `_held_out_count` — which rejects "a marker object, not a
        # held-out case" — and `_judge_issues`). Measured: `should_fire: [null]` /
        # `should_not_fire: [null]` PASSED tier L as "routing eval asserts both
        # polarities", a lens gated on a suite containing no prompts.
        if isinstance(v, list) and _substantive(v):
            ks = str(k)
            if ks in _POSITIVE_KEYS:
                pos = True
            elif ks in _NEGATIVE_KEYS:
                neg = True
    for key in ("cases", "prompts", "tests"):
        cases = data.get(key)
        if not isinstance(cases, list):
            continue
        for case in cases:
            cp, cn = _case_polarity(case)
            if cp and cn:
                continue  # one case cannot be both; it asserts nothing
            pos, neg = pos or cp, neg or cn
    return pos, neg


def _routing_eval_issue(skill_dir: Path, blobs: list[tuple[Path, dict]],
                        unparseable: list[_Unparseable]) -> str | None:
    """Tier L's core: a routing eval asserting BOTH polarities. A positive-only suite
    structurally cannot see over-triggering, which is the failure mode a lens has."""
    if unparseable:
        return (f"{len(unparseable)} eval artifact(s) could not be trusted "
                f"({_unparseable_detail(unparseable[0])}); "
                "an unverifiable routing eval is not a routing eval")
    # Polarity is read ONLY from a top-level cases/prompts/tests list. Walking the
    # whole document let unrelated nested metadata supply it —
    # {"metadata": {"should_fire": true}, "judge": {"should_trigger": false}} passed
    # tier L with no routing cases at all.
    pos = neg = False
    for _, data in blobs:
        bp, bn = _blob_polarity(data)
        pos, neg = pos or bp, neg or bn
    if pos and neg:
        return None
    if not pos and not neg:
        return ("no routing eval — a lens is gated on firing on the right requests "
                "and staying silent on near-misses")
    missing = "negative (should_not_fire)" if not neg else "positive (should_fire)"
    return (f"routing eval asserts only one polarity — missing a {missing} case; "
            "a positive-only suite cannot see over-triggering")


def _tier_of(skill_dir: Path, fm: dict, core: list[str],
             code: list[str] | None = None) -> tuple[str | None, bool, str]:
    """Return (tier, declared, why). Declared wins; otherwise infer.

    Inference exists so a 94-skill roster does not break the day tiers ship — NOT to
    let an unclassifiable skill through. `None` means the gate could not tell what
    kind of thing this is, and that is a FAIL, same as before.

    Inference fires for D ONLY. Shipping a pure function is definitionally tier D, so
    that one is safe. The tempting second rule — "has a trigger eval, no code -> L" —
    is NOT: a routing eval is tier L's *core*, not its *signature*, and every tier can
    carry one. Backfilling the roster with that rule labelled `autonomous`, `handoff`
    and `checkit` as lenses; all three run pipelines and none is a lens. A confidently
    wrong tier is worse than an absent one (BRO-2192).
    """
    dup = _duplicate_top_level_key_issue(skill_dir / "SKILL.md")
    if dup:
        return None, False, dup
    raw = _fm(fm, "tier")
    raw = "" if raw is None else str(raw).strip().upper()
    if raw in TIERS:
        return raw, True, "declared"
    if raw:
        return None, False, f"tier: {raw!r} is not one of D/J/L"
    if core:
        return TIER_D, False, "inferred: ships scripts/ code"
    # "no scripts/ code" was FALSE for the case that motivated the split: a skill
    # shipping `scripts/test_only.py` ships scripts/ code, it just ships no CORE.
    # Saying otherwise sent an author looking for a file that is already there.
    if code:
        return None, False, ("no tier: declared, and no script here is a deterministic "
                             "core — each is a test, pytest configuration, or empty "
                             "(J and L must be declared)")
    return None, False, "no tier: declared and no scripts/ code (J and L must be declared)"


def run_checklist(skill_dir: Path, *, roles_dir: Path | None, registry: Path | None,
                  entities_dir: Path | None, strict: bool, run_tests: bool = False,
                  skills_sh: str | None = None) -> list[dict]:
    fm = parse_frontmatter(skill_dir / "SKILL.md")
    name = _fm(fm, "name") or skill_dir.resolve().name
    latent_only = str(_fm(fm, "latent_only", "")).lower() in ("true", "yes", "1")
    code = _code_files(skill_dir)
    blobs, unparseable_evals = _eval_blobs(skill_dir)
    core = _core_files(skill_dir)
    tier, tier_declared, tier_why = _tier_of(skill_dir, fm or {}, core, code)
    results: list[dict] = []

    def add(step, label, status, detail, required=False):
        results.append({"step": step, "label": label, "status": status,
                        "detail": detail, "required": required})

    # 1 — SKILL.md contract (required): frontmatter present + skills.sh-parseable.
    gotcha = _skillsh_frontmatter_issue(skill_dir)
    if not (fm and _fm(fm, "name") and _fm(fm, "description")):
        add(1, "SKILL.md contract", FAIL,
            "SKILL.md missing" if fm is None else "frontmatter needs name + description", required=True)
    elif gotcha:
        add(1, "SKILL.md contract", FAIL,
            f"frontmatter breaks skills.sh parser (multi-quoted-string list item): {gotcha[:48]}", required=True)
    else:
        add(1, "SKILL.md contract", PASS, f"name={_fm(fm, 'name')} (skills.sh-parseable)", required=True)

    # 1b — Installable layout (ADVISORY, not required). A top-level SKILL.md is
    # standard-valid (the agentskills.io spec + the skills.sh README list the repo
    # ROOT as a discovery location). BUT a *remote* `npx skills add <owner>/<repo>`
    # of a repo-root skill with sibling dirs drops them — an open upstream bug
    # (vercel-labs/skills#1523, unfixed). So this is a WARN, not a FAIL: the skill
    # is correctly authored; the install path is buggy. Fix = vendor into a
    # `skills/<name>/` subdir (canonically the `broomva/skills` monorepo, where the
    # subdir is non-redundant). Verify with a clean-room runnable install.
    layout = _repo_root_bundled_dirs_issue(skill_dir)
    if layout:
        add("1b", "Installable layout", WARN,
            f"{layout} (standard-valid layout, but hits skills.sh#1523 on remote install — "
            f"prefer skills/<name>/ in the broomva/skills monorepo)", required=False)
    else:
        add("1b", "Installable layout", PASS, "skills/<name>/ subdir (or single-file) — installs cleanly")

    # 1c — Reference integrity (required): SKILL.md / skill.json / templates must
    # not advertise files that do not exist. The #1 real defect (broken contracts):
    # a skill installs fine, but an agent following its SKILL.md invokes a missing
    # script/template. Fix = ship the file or mark the reference Planned.
    ref_issues = _internal_ref_issues(skill_dir)
    if ref_issues:
        shown = "; ".join(ref_issues[:3]) + ("; …" if len(ref_issues) > 3 else "")
        add("1c", "Reference integrity", FAIL,
            f"{len(ref_issues)} broken reference(s): {shown} — ship the file or mark Planned",
            required=True)
    else:
        add("1c", "Reference integrity", PASS,
            "every scripts/references/assets/templates reference resolves", required=True)

    # 2 — Tier + its core (required). The gate no longer asks the single question
    # "is there a deterministic core?" — that let a testability question decide an
    # expressibility question, and it gated NOTHING on the `latent_only` branch.
    # Step 2 now asks what KIND of skill this is and applies that tier's gate.
    # Inference picks WHICH gate when `tier:` is absent; it never waives one.
    tag = "tier " + (tier or "?") + (" (declared)" if tier_declared else f" ({tier_why})")
    tier_warns: list[str] = []

    # Syntax-check EVERY shipped script, whatever the tier. This deliberately sits
    # OUTSIDE the tier branches: an earlier draft called _script_syntax_error only
    # inside the tier-D arm, so declaring `tier: L` silently bought a skill out of a
    # syntax check that origin/main applied unconditionally — a coverage regression
    # introduced by the refactor and caught in adversarial review.
    broken = [(c, e) for c in code if (e := _script_syntax_error(skill_dir / c))]
    # The empty set is drawn from CANDIDATES, not from all code: an empty
    # `scripts/__init__.py` beside a working `scripts/core.py` is an ordinary package
    # marker, and failing the skill for it was a false reject (round 20).
    empty_core = [c for c in _core_candidates(skill_dir)
                  if not _has_executable_content(skill_dir / c)
                  and Path(c).name.lower() not in _PACKAGE_PLUMBING]

    # A file that does not parse is the most actionable thing the gate can say, so it
    # is said FIRST. It used to sit behind `tier is None`, which meant a skill whose
    # only script was broken reported "cannot classify" — true, but it buried the
    # reason it could not be classified.
    if broken:
        add(2, "Tier + core", FAIL,
            f"{tag}: " + "; ".join(f"{c}: {e}" for c, e in broken[:3]), required=True)
    elif tier is None:
        add(2, "Tier + core", FAIL,
            f"cannot classify — {tier_why}. Declare `tier: D` (ship scripts/), "
            "`tier: J` (ship evals/admission.md + rubric + held-out cases + judge config), "
            "or `tier: L` (ship a both-polarity routing eval). If this skill is a "
            "PROCEDURE binding an external capability (a CLI, an API, a hosted runtime) "
            "it is none of the three — that residue is BRO-2192, and until it lands the "
            "honest options are an integration test (step 4) or an explicit tier", required=True)
    elif latent_only and (_det := _deterministic_scripts(skill_dir)):
        # Deliberately NOT `core`: see _deterministic_scripts. A lens may ship a test
        # and an empty package marker; what it may not ship is anything that runs.
        add(2, "Tier + core", FAIL,
            f"latent_only:true but {len(_det)} deterministic script(s) present "
            f"({', '.join(_det[:3])}) — contradiction", required=True)
    elif empty_core:
        # An empty file is not a deterministic core. py_compile is perfectly happy
        # with 0 bytes, so `touch scripts/noop.py` used to satisfy tier D. An earlier
        # attempt moved this inside the tier-D arm to spare an empty `__init__.py`;
        # that made it unreachable whenever a core existed, so an empty stub beside a
        # real core started passing. The marker is spared by not counting plumbing.
        add(2, "Tier + core", FAIL,
            f"{tag}: empty script(s) {', '.join(empty_core[:3])} "
            "— an empty file is not a core", required=True)
    elif tier == TIER_D:
        if not core:
            add(2, "Tier + core", FAIL,
                "tier D declared but no scripts/ code that is not itself a test "
                "or pytest configuration" if code
                else "tier D declared but no scripts/ code", required=True)
        else:
            checked = [c for c in code if _syntax_checkable(skill_dir / c)]
            claim = (f"{len(code)} script(s), syntax ok" if len(checked) == len(code)
                     else f"{len(code)} script(s), {len(checked)} syntax-checked "
                          f"({len(code) - len(checked)} unchecked: no checker for their type)")
            # The step is labelled "Tier + core". Reporting only the script count made
            # the split invisible in the one line a reader sees.
            if len(core) != len(code):
                claim += f"; {len(core)} core"
            unchecked = [c for c in code if not _syntax_checkable(skill_dir / c)]
            if strict and unchecked:
                # Disclosing that a file was not syntax-checked is honest; ACCEPTING
                # it under --strict is not. A `.ts` core nothing examined passes on a
                # box without node and fails on one with it, which is the
                # environment-dependent verdict --strict exists to refuse.
                add(2, "Tier + core", FAIL,
                    f"{tag}: (--strict) {len(unchecked)} script(s) could not be "
                    f"syntax-checked here: {', '.join(unchecked[:3])} — install the "
                    "missing checker (node for .mjs/.js/.ts) or drop --strict; a "
                    "verdict that depends on the box is not a verdict", required=True)
            else:
                add(2, "Tier + core", PASS,
                    f"{tag}: {claim}: {', '.join(core[:3])}", required=True)
    elif tier == TIER_J:
        issues: list[str] = []
        if unparseable_evals:
            issues.append(f"{len(unparseable_evals)} eval artifact(s) could not be "
                          f"trusted ({_unparseable_detail(unparseable_evals[0])})")
        if (adm := _admission_issue(skill_dir)):
            issues.append(adm)
        if (rub := _rubric_issue(skill_dir, blobs)):
            issues.append(rub)
        if (n_held := _held_out_count(skill_dir, blobs)) == 0:
            issues.append("no held-out cases (evals/held-out/ or cases flagged held_out); "
                          "an empty file or a README is not a case")
        jf, jw = _judge_issues(blobs)
        issues += jf
        tier_warns += jw
        if issues:
            shown = "; ".join(issues[:3]) + ("; …" if len(issues) > 3 else "")
            add(2, "Tier + core", FAIL, f"{tag}: {len(issues)} gap(s): {shown}", required=True)
        else:
            add(2, "Tier + core", PASS,
                f"{tag}: admission recorded, rubric + {n_held} held-out case(s), "
                "cross-model judge with a measured floor", required=True)
    else:  # TIER_L
        if (iss := _routing_eval_issue(skill_dir, blobs, unparseable_evals)):
            add(2, "Tier + core", FAIL, f"{tag}: {iss}", required=True)
        else:
            add(2, "Tier + core", PASS,
                f"{tag}: routing eval asserts both polarities", required=True)

    # Warnings are appended AFTER step 2 so the human output reads in step order; an
    # earlier draft printed "Judge distinctness" above "Tier + core".
    for w in tier_warns:
        add("2j", "Judge distinctness", WARN, w)
    if tier == TIER_J:
        # The judge itself is an unbuilt seam. Reporting its RUN as a PASS because the
        # artifacts exist would be exactly the vacuous pass this harness exists to
        # prevent, so it is a named SKIP either way.
        add("2j*", "Judge execution", SKIP,
            "LLM judge is a declared seam — skill_evals/checks.py:make_judge_check "
            "raises rather than stubbing a pass; tier J gates artifacts, not judged output")
    if tier and not tier_declared:
        add("2t", "Tier declaration", WARN,
            f"no `tier:` in frontmatter; {tier_why} → treated as {tier}. Declare it explicitly.")

    # 3 — Unit tests: present + REAL (non-empty, test construct) [+ run if asked]
    # Tests are required whenever deterministic code ships, whatever the tier. The
    # old expression routed through `latent_only`, which is how a skill could ship
    # scripts and buy its way out of testing them.
    # NOT `core`, and not `code` either. `core` excludes `conftest.py` BY NAME, so
    # requiring tests off it meant renaming one file bought a working module out of
    # being tested — the round-21 fail-open, transplanted. `code` was the original
    # bug (a package marker is not a thing to test). The right predicate is the
    # conjunction: a file is excused only when its NAME and its STRUCTURE agree it
    # is a test, and for non-Python the structure must show a real construct.
    require_tests = bool(_deterministic_scripts(skill_dir))
    all_tests = _test_files(skill_dir)
    real_tests = [t for t in all_tests if _is_real_test(skill_dir / t)]
    if not require_tests:
        add(3, "Unit tests", SKIP if not real_tests else PASS,
            # "no code to test" became false the moment require_tests started
            # reading `core`: a lens shipping a test and a package marker has code.
            # Same class as the two other messages this arc had to correct — a string
            # that describes the OLD predicate after the predicate moved.
            "nothing deterministic to test" if not real_tests
            else f"{len(real_tests)} test file(s)")
    elif not real_tests:
        why = "no tests/" if not all_tests else f"{len(all_tests)} test file(s) but none contain a real test"
        add(3, "Unit tests", FAIL, f"{why} — the 'works today' trap", required=True)
    elif run_tests:
        rc = subprocess.run([sys.executable, "-m", "pytest", "-q", str(skill_dir / "tests")],
                            capture_output=True, text=True).returncode if (skill_dir / "tests").is_dir() else 0
        add(3, "Unit tests", PASS if rc == 0 else FAIL,
            f"{len(real_tests)} test file(s); pytest {'green' if rc == 0 else 'FAILED'}", required=True)
    else:
        add(3, "Unit tests", PASS, f"{len(real_tests)} real test file(s): {', '.join(real_tests[:3])}", required=True)

    # 4 — Integration tests (recommended; never force-required)
    integ = _test_files(skill_dir, "integration") or _test_files(skill_dir, "integ")
    add(4, "Integration tests", PASS if integ else WARN,
        f"{len(integ)} file(s)" if integ else "none (recommended for live-endpoint skills)", required=False)

    # 5 — LLM evals (recommended). Presence is NOT correctness: this check used to
    # pass on `(skill_dir / "evals").is_dir()` alone, so an EMPTY evals/ dir scored
    # "present". That is the same trap step 3 already avoids via _is_real_test, and
    # it is why a stack can report ~10% "eval coverage" while containing ZERO
    # trigger assertions (BRO-2005 audit: 38/376 skills with an eval artifact, 0
    # with a single should_trigger case). A skill's LATENT half — does the
    # description fire, does it stay silent on a near-miss — is exactly the half
    # a presence check cannot see, so grade the CONTENT.
    #
    # Tier J's eval artifacts (rubric / held-out cases / judge) are gated in step 2,
    # NOT here. Step 5 grades the TRIGGER surface; re-requiring it for J would be a
    # second gate over the same evidence, and a weaker one — step 2 validates the
    # judge is cross-model and the floor is measured, which a presence scan cannot.
    eval_files = _eval_files(skill_dir)
    trigger_evals = [f for f in eval_files if _is_trigger_eval(skill_dir / f)]
    if trigger_evals:
        add(5, "LLM evals", PASS,
            f"{len(trigger_evals)} trigger eval(s): {', '.join(trigger_evals[:3])}", required=False)
    elif eval_files:
        add(5, "LLM evals", WARN,
            f"{len(eval_files)} eval artifact(s) but none assert trigger behaviour "
            f"({'/'.join(sorted(TRIGGER_ASSERTION_KEYS)[:3])}…) — latent half still ungated",
            required=False)
    else:
        add(5, "LLM evals", WARN, "none (recommended for judgment-output skills)", required=False)

    # 6 — Resolver trigger (workspace-aware; under --strict the missing path is
    # itself a FAIL — strict must not pass while skipping the checks it exists for)
    if registry is None:
        add(6, "Resolver trigger", FAIL if strict else SKIP,
            "(--strict) requires --registry <roles/_index.md|AGENTS.md>" if strict
            else "pass --registry <roles/_index.md> to check", required=strict)
    else:
        add(6, "Resolver trigger", *(_check_registry(registry, name)), required=strict)

    # 7 — Resolver eval (workspace-aware; missing path FAILs under --strict).
    # Required for tier L *when a roles dir is supplied*: a lens whose whole claim is
    # "it changes what you attend to" is gated on routing. It is NOT made required
    # when --roles-dir is absent — that would fail every lens on a repo-local run for
    # the absence of a flag rather than the absence of an eval.
    l_needs_resolver = tier == TIER_L and roles_dir is not None
    if roles_dir is None:
        add(7, "Resolver eval", FAIL if strict else SKIP,
            "(--strict) requires --roles-dir" if strict else "pass --roles-dir to check", required=strict)
    else:
        evalf = roles_dir / f"{name}.eval.yaml"
        ok = evalf.is_file()
        req = strict or l_needs_resolver
        add(7, "Resolver eval", PASS if ok else (FAIL if req else WARN),
            f"{evalf.name} present" if ok
            else f"no {name}.eval.yaml (skillify step 7)" + (" — required for tier L" if l_needs_resolver else ""),
            required=req)

    # 8 — check-resolvable + DRY (external registry-wide tool)
    add(8, "Check-resolvable + DRY", SKIP, "run `bstack skills audit` (registry-wide, not per-skill)")

    # 9 — E2E smoke (recommended; --skills-sh runs a real registry install-list)
    if skills_sh:
        ok, detail = _skillsh_list_has(skills_sh, name)
        add(9, "E2E smoke test", PASS if ok else FAIL, detail, required=True)
    else:
        smoke = _test_files(skill_dir, "smoke") or (skill_dir / "tests" / "smoke.sh").is_file()
        add(9, "E2E smoke test", PASS if smoke else WARN,
            "present" if smoke else "none (recommended; --skills-sh <repo> for a real install-list)", required=False)

    # 10 — Brain filing / provenance (workspace-aware)
    if entities_dir is None:
        add(10, "Brain filing rules", SKIP, "pass --entities-dir to check KG provenance")
    else:
        prov = entities_dir.is_dir() and any(
            re.search(rf"\b{re.escape(name)}\b", _read(p) or "")
            for p in entities_dir.rglob("*.md"))
        add(10, "Brain filing rules", PASS if prov else WARN,
            f"'{name}' referenced in knowledge graph" if prov else f"no KG entity references '{name}'", required=False)

    return results


def _check_registry(registry: Path, name: str) -> tuple[str, str]:
    """Step 6: require the skill name in a STRUCTURED registry line (table row,
    list item, or backticked) — a bare prose mention is not 'registered'."""
    if not registry.is_file():
        return FAIL, f"{registry} not found"
    # The name must be the ENTRY itself — the first token of a list item, or a
    # table cell that *starts* with the name — not merely present somewhere on a
    # bulleted/piped line (M3: "- we removed `demo`" and "x | demo y" must FAIL).
    nb = re.escape(name)
    list_item = re.compile(r"^[-*]\s+[\W_]*" + nb + r"\b")
    # `_read`, the fourth member of the shared reader surface: this was the ONE read
    # in the file that bypassed it with no local try, so an unreadable registry
    # (PermissionError) produced a bare traceback and zero checklist lines — the
    # "reported, never thrown" contract again, at the last site holding out.
    raw_registry = _read(registry)
    if raw_registry is None:
        return WARN, f"registry {registry.name} is unreadable — cannot verify the trigger"
    for raw in raw_registry.splitlines():
        s = raw.strip()
        if list_item.match(s):
            return PASS, f"'{name}' registered (list item) in {registry.name}"
        # treat as a table row only if it's actually table-shaped (≥2 pipes or a
        # leading pipe) — a single stray '|' in prose is not a table cell
        if s.count("|") >= 2 or s.startswith("|"):
            for cell in s.split("|"):
                c = cell.strip().strip("`* ")
                c = re.sub(r"^\[", "", re.sub(r"\]\(.*$", "", c))  # [name](target) -> name
                if re.match(r"^" + nb + r"\b", c):
                    return PASS, f"'{name}' registered (table cell) in {registry.name}"
    return FAIL, f"'{name}' not a registry entry in {registry.name} (prose/backtick mention ≠ registered)"


def survey(root: Path, **kw) -> dict:
    """Run the checklist over every SKILL.md under `root` and tally by tier.

    This is the SAME gate over a population, not a second gate — the distinction
    matters, because a bespoke measurement apparatus built alongside a gate ends up
    being the thing that gets hardened. Every roster count in SKILL.md is regenerated
    by this, so a claim about the roster is never a number someone remembered.
    """
    rows: list[dict] = []
    for md in sorted(root.rglob("SKILL.md")):
        d = md.parent
        # `.venv` and friends are here because DOGFOODING THE MERGED ARTIFACT found
        # them: run this on a developer machine and third-party packages that ship
        # their own SKILL.md — logfire, typer, fastapi — are counted as skills of
        # this repo. The passing count is unaffected (they all fail), but the
        # denominator inflates from 96 to 99, and SKILL.md quotes 96. A roster
        # number that changes with whether someone has installed dependencies is
        # not a roster number.
        if any(part in {"node_modules", ".git", "__pycache__", ".pytest_cache",
                        ".worktrees", ".venv", "venv", "site-packages", ".tox"}
               for part in d.parts):
            continue
        # One odd file mode anywhere must not cost the whole report. This is the
        # command the docs tell a reader to run to regenerate the roster numbers;
        # an uncaught OSError two-thirds of the way through produced ZERO output.
        try:
            fm = parse_frontmatter(md) or {}
            tier, declared, why = _tier_of(d, fm, _core_files(d), _code_files(d))
            res = run_checklist(d, **kw)
            failed = [f"{r['step']} {r['label']}" for r in res
                      if r["required"] and r["status"] != PASS]
        except Exception as exc:  # a skill that cannot be checked is not a skill that passed
            fm, tier, declared, why = {}, "errored", False, f"errored: {type(exc).__name__}"
            failed = [f"error: {type(exc).__name__}: {exc}"[:120]]
        rows.append({
            "skill": _fm(fm, "name") or d.name,
            "path": str(d.relative_to(root)) if d.is_relative_to(root) else str(d),
            "tier": tier, "declared": declared, "why": why,
            "failed": failed,
            "ok": not failed,
        })
    by_tier: dict[str, int] = {}
    for r in rows:
        key = (r["tier"] or "unclassified") + ("" if r["declared"] else " (inferred)")
        by_tier[key] = by_tier.get(key, 0) + 1
    return {"root": str(root), "total": len(rows), "by_tier": by_tier,
            "passing": sum(1 for r in rows if r["ok"]),
            "failing": sum(1 for r in rows if not r["ok"]), "rows": rows}


def _print_survey(rep: dict) -> None:
    print(f"skillify tier survey — {rep['root']}\n")
    print(f"  {rep['total']} skill(s); {rep['passing']} pass the gate, {rep['failing']} fail\n")
    for k in sorted(rep["by_tier"]):
        print(f"    {k:<24} {rep['by_tier'][k]:>4}")
    print()
    failing = [r for r in rep["rows"] if not r["ok"]]
    if failing:
        print("  failing:")
        for r in failing:
            print(f"    ✗ {r['skill']:<28} tier={r['tier'] or '?':<3} {', '.join(r['failed'][:2])}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="skillify-check",
        description="Run the 10-step skillify readiness checklist on a skill directory.")
    ap.add_argument("skill_dir", nargs="?", help="path to the skill directory (contains SKILL.md)")
    ap.add_argument("--survey", metavar="ROOT",
                    help="run the checklist over every SKILL.md under ROOT and tally by tier "
                         "(the same gate over a population — regenerates the roster counts)")
    ap.add_argument("--roles-dir", default=None, help="workspace roles/ dir (enables step 7)")
    ap.add_argument("--registry", default=None, help="AGENTS.md or registry file (enables step 6)")
    ap.add_argument("--entities-dir", default=None, help="research/entities dir (enables step 10)")
    ap.add_argument("--strict", action="store_true", help="require steps 6+7 (and fail if their path flag is missing)")
    ap.add_argument("--run-tests", action="store_true", help="actually run pytest for step 3 (not just detect)")
    ap.add_argument("--skills-sh", default=None, metavar="REPO_OR_PATH",
                    help="step 9: run `npx skills add <REPO_OR_PATH> --list` and require the skill is listed (real skills.sh install-verify)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    common = dict(
        roles_dir=Path(args.roles_dir) if args.roles_dir else None,
        registry=Path(args.registry) if args.registry else None,
        entities_dir=Path(args.entities_dir) if args.entities_dir else None,
        strict=args.strict, run_tests=args.run_tests, skills_sh=args.skills_sh)

    if args.survey and args.skill_dir:
        print("[skillify] --survey and a skill_dir are different modes; pass one",
              file=sys.stderr)
        return 2
    if args.survey:
        root = Path(args.survey)
        if not root.is_dir():
            print(f"[skillify] not a directory: {root}", file=sys.stderr)
            return 2
        rep = survey(root, **common)
        print(json.dumps(rep, indent=2) if args.json else "", end="")
        if not args.json:
            _print_survey(rep)
        return 0  # a survey REPORTS; it does not gate. Use the per-skill run to gate.

    if not args.skill_dir:
        print("[skillify] need a skill_dir (or --survey ROOT)", file=sys.stderr)
        return 2
    skill_dir = Path(args.skill_dir)
    if not skill_dir.is_dir():
        print(f"[skillify] not a directory: {skill_dir}", file=sys.stderr)
        return 2

    results = run_checklist(skill_dir, **common)

    # A required step fails the gate unless it PASSed (SKIP only counts as
    # non-failing for non-required steps; a required SKIP can't happen — required
    # workspace steps WARN/ FAIL instead when their input is missing under strict).
    failed = [r for r in results if r["required"] and r["status"] != PASS]
    warned = [r for r in results if r["status"] == WARN]
    disp = skill_dir.resolve().name or str(skill_dir)

    if args.json:
        print(json.dumps({"skill": disp, "results": results,
                          "failed": len(failed), "warned": len(warned)}, indent=2))
        return 1 if failed else 0

    glyph = {PASS: "✓", WARN: "▲", FAIL: "✗", SKIP: "·"}
    print(f"skillify checklist — {disp}\n")
    for r in results:
        req = " (required)" if r["required"] else ""
        print(f"  {glyph[r['status']]} {r['step']:>2}. {r['label']:<24} {r['status']:<4} {r['detail']}{req}")
    print()
    if failed:
        print(f"✗ FAIL — {len(failed)} required step(s) incomplete; {len(warned)} warning(s). "
              "Not a skill yet — just code that works today.")
        return 1
    print(f"✓ PASS — all required steps complete ({len(warned)} recommended warning(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
