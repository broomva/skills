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
- `latent_only: true` is only honored when NO deterministic code is present
  (declaring it while shipping scripts is a contradiction → FAIL), and it makes
  step 5 (trigger evals) REQUIRED — a skill with no deterministic half has no
  other gate on its behaviour at all.
- Step 1 validates the frontmatter against the agentskills.io spec (description
  ≤1024, name ≤64 + charset, compatibility ≤500), not merely that the fields
  exist. Presence-as-validity was satisfiable by construction.

Advisory sub-steps (WARN, never gate): 1d description carries a when-clause,
1e body carries a gotchas section, 1f body under 500 lines.

Required steps gate the exit code: 1 (SKILL.md contract), 2 (code syntax — unless
genuinely latent), 3 (real unit tests, when code present), 5 (trigger evals, when
purely latent). Workspace-aware steps
(6 resolver trigger, 7 resolver eval, 10 brain filing) SKIP unless their path
flag is supplied. `--strict` promotes 6/7 to required *and* fails if their path
flag is missing (so strict can't pass while skipping the things strict is for).

Pure-stdlib + optional pyyaml/node; deterministic; zero network.
"""
from __future__ import annotations

import argparse
import ast
import json
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

CODE_EXTS = {".py", ".sh", ".mjs", ".js", ".ts"}
_TEST_CODE_EXTS = ("py", "sh", "mjs", "js", "ts")
PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"

# --- agentskills.io spec conformance -----------------------------------------
# Normative limits, https://agentskills.io/specification (read verbatim 2026-08-10):
#   name         Max 64 chars, lowercase [a-z0-9-], no leading/trailing/consecutive hyphen
#   description  Max 1024 chars, non-empty
#   compatibility  Max 500 chars (optional field)
#
# These are CONFORMANCE limits and they are TIGHTER than the render cap this host
# happens to apply. BRO-2014 measured the observed cap at 1536 chars across 1,199
# real skill_listing attachments — so a description of 1025..1536 renders in FULL
# here and is still invalid under the standard. That gap is the "silent band": no
# local signal fires, and the skill breaks only when some other conforming host
# loads it. Conform to the tighter number; measure the looser one to know the slack.
# See research/entities/concept/observed-limit-is-not-the-conformance-limit.md
SPEC_MAX_DESCRIPTION = 1024
SPEC_MAX_NAME = 64
SPEC_MAX_COMPATIBILITY = 500
SPEC_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
OBSERVED_RENDER_CAP = 1536  # measured, NOT normative — for message precision only

# Body length is a DIFFERENT cost with a DIFFERENT schedule. The body loads only
# on trigger, so an over-long body is a per-trigger *dilution* risk; the
# description is billed on EVERY turn and gates triggering. Ranking skills by body
# length audits the surface most of them never pay for, so this is a WARN and
# never gates the exit code, while a spec-invalid description is a hard FAIL.
# See research/entities/concept/trigger-surface-is-the-standing-cost.md
SPEC_RECOMMENDED_BODY_LINES = 500

# IBM Technology, "5 Best Practices for Building AI Agent Skills" (2026-08-10):
# "the name and the description need to contain enough information by themselves
# so that the agent knows when to use it … models tend to undertrigger."  A
# description that says what a skill DOES but never when to USE it is the
# single most common trigger defect, so require the when-clause to be present.
# Accepts the common affirmative trigger phrasings ("invoke for", "use this for"
# are legitimate and were previously warned on) and rejects negated ones — "do
# NOT use when …" describes an anti-trigger, so counting it as a when-clause
# would score a description that never says when to fire as if it did.
_WHEN_CLAUSE_RE = re.compile(
    r"(?<!not )(?<!never )\b("
    r"use\s+when|used\s+when|use\s+this\s+when|use\s+this\s+for|use\s+for|"
    r"triggers?\s+on|when\s+to\s+use|invoke\s+(?:for|when)|reach\s+for\s+(?:this\s+)?when"
    r")\b", re.I)
# The window has to cover real hedging — "do not UNDER ANY CIRCUMSTANCES use
# when …" is four words, and a two-word window let it read as affirmative.
# A BARE `not` is deliberately absent from the negator set: with a six-word
# window it swallows affirmative constructions like "Not only should you use
# when offline". Every negator here is an explicit multi-word negation, which is
# a closed set — unlike "any sentence containing 'not'", which is not.
_WHEN_NEGATION_RE = re.compile(
    r"\b(?:do\s+not|does\s+not|don't|doesn't|never|avoid|rather\s+than)\s+"
    r"(?:\w+[\s,]+){0,6}?"
    r"(?:use|used|using|invoke|invoked|trigger|triggers|reach\s+for)\b", re.I)

# Same source, practice 2: "the highest value section you can put in the skill
# body is gotchas — environment-specific facts that defy reasonable assumptions.
# Every time you correct the agent by hand, that correction is a gotcha."  A
# skill distilled from a real session but carrying no corrections has thrown away
# the only content the model could not have produced on its own.
# CommonMark allows an ATX heading to be indented up to 3 spaces. Anchoring at
# column zero meant an indented `## Gotchas` was not seen as a heading at all —
# which also made the indented-fence test pass for the wrong reason: it was
# proving "indented headings are invisible", not "fences are stripped".
_GOTCHA_SECTION_RE = re.compile(
    r"^ {0,3}#{1,6}\s.*\b(gotchas?|pitfalls?|anti-?rationaliz\w*|caveats?|"
    r"common\s+mistakes?|troubleshooting|known\s+issues?|failure\s+modes?|"
    r"red\s+flags?|what\s+goes\s+wrong)\b", re.I | re.M)
# A heading that DENIES the section — "## No gotchas", "## No known gotchas" —
# must not satisfy a check that the corrections were written down. Scanned
# across the whole heading prefix, not just the word immediately before.
_NEGATED_HEADING_RE = re.compile(r"\b(no|none|zero|without|nil|not|never)\b", re.I)


# --- frontmatter -------------------------------------------------------------

def parse_frontmatter(md_path: Path) -> dict | None:
    """Return the top YAML frontmatter as a flat str dict, or None if absent.

    Uses pyyaml when available (correctly handles folded/block scalars like
    `description: >-`); falls back to a scalar-only hand-roll that skips
    indented continuation lines so folded prose can't manufacture bogus keys.
    """
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        return None
    # Delimiters must be WHOLE lines: a bare `\n---` substring test lets a body
    # line like `---8<---` close the block early, truncating the frontmatter that
    # every downstream check then validates.
    m = re.match(r"^---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)", text, re.DOTALL)
    if not m:
        return None
    block = m.group(1)
    try:
        import yaml  # optional
        data = yaml.safe_load(block)
        if isinstance(data, dict):
            return {k: (v if isinstance(v, str) else str(v)) for k, v in data.items()}
    except Exception:
        pass
    fm: dict[str, str] = {}
    for line in block.splitlines():
        if line[:1] in (" ", "\t") or line.lstrip().startswith("#"):
            continue  # indented continuation / comment — not a key
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip("\"'")
    return fm


def _frontmatter_type_issues(md_path: Path) -> list[str]:
    """Malformed YAML and wrong-typed fields, which `parse_frontmatter` hides.

    `parse_frontmatter` is lenient by design — it stringifies non-str values and
    falls back to a hand-rolled scan when YAML fails, so callers always get a
    flat str dict. That leniency silently launders real defects past step 1:
    `description: [foo]` becomes the 7-char string "['foo']" and passes the 1024
    check, while the registry linter rejects the same file as a non-string. Two
    gates, one contract, opposite answers. Detect the raw shape here.
    """
    if yaml is None:
        # Fail LOUD, not open. Without a YAML parser this check cannot run, and
        # silently returning "no issues" is indistinguishable from "validated" —
        # the exact confusion the rest of this file exists to remove.
        return ["PyYAML unavailable — frontmatter types were NOT validated "
                "(install pyyaml, or run the registry linter which requires it)"]
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        return []
    m = re.match(r"^---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)", text, re.DOTALL)
    if not m:
        return []
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        return [f"frontmatter is not valid YAML — {str(e).splitlines()[0]}"]
    if not isinstance(data, dict):
        return ["frontmatter is not a mapping"]
    out = []
    for field in ("name", "description", "compatibility"):
        if field in data and not isinstance(data[field], str):
            got = type(data[field]).__name__
            out.append(f"`{field}` must be a string, got {got}")
    return out


def _spec_violations(fm: dict) -> list[str]:
    """Hard agentskills.io violations — each makes the skill invalid under the
    standard regardless of whether THIS host tolerates it.

    Deliberately NOT checked here: the spec's `name` must-match-parent-directory
    rule. `skillify_check` is routinely pointed at a scratch/temp/CI checkout
    whose directory name is not the canonical one, so enforcing it here would
    manufacture false positives. It is enforced where the canonical layout is
    known — the registry-wide `.github/workflows/lint-skill-md.yml`.
    """
    out: list[str] = []
    name = fm.get("name") or ""
    desc = fm.get("description") or ""

    # Spec §compatibility: "Must be 1-500 characters IF PROVIDED" — present-but-
    # empty is invalid, which `fm.get(...) or ""` would collapse into "absent".
    if "compatibility" in fm:
        compat = fm["compatibility"]
        if not compat.strip():
            out.append("compatibility is present but empty (spec: 1-500 chars)")
        elif len(compat) > SPEC_MAX_COMPATIBILITY:
            out.append(f"compatibility {len(compat)} chars > {SPEC_MAX_COMPATIBILITY} spec max")

    if len(desc) > SPEC_MAX_DESCRIPTION:
        band = ("renders in full here but is non-conforming — the silent band"
                if len(desc) <= OBSERVED_RENDER_CAP
                else f"also truncated mid-sentence past {OBSERVED_RENDER_CAP} by the renderer")
        out.append(f"description {len(desc)} chars > {SPEC_MAX_DESCRIPTION} spec max ({band})")
    if len(name) > SPEC_MAX_NAME:
        out.append(f"name {len(name)} chars > {SPEC_MAX_NAME} spec max")
    elif not SPEC_NAME_RE.match(name):
        out.append(f"name '{name}' must be lowercase [a-z0-9-] with no leading, "
                   "trailing or consecutive hyphens")
    return out


def _body_after_frontmatter(skill_dir: Path) -> str:
    """SKILL.md text with the YAML frontmatter stripped (empty string if absent)."""
    try:
        text = (skill_dir / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    m = re.match(r"^---\n.*?\n---\n?", text, re.DOTALL)
    return text[m.end():] if m else text


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
        text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
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
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    if name.startswith("test_") and ext in _TEST_CODE_EXTS:
        return True
    if any(name.endswith(f"_test.{e}") for e in _TEST_CODE_EXTS):
        return True
    return bool(re.search(r"\.test\.(py|sh|mjs|js|ts)$", name))


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


def _code_files(skill_dir: Path) -> list[str]:
    found = {
        str(f.relative_to(skill_dir))
        for f in _iter_files(skill_dir, ("scripts", ""))
        if f.suffix in CODE_EXTS and not _is_test_file(f.name)
        and f.name not in {"__init__.py", "conftest.py", "setup.py"}
    }
    return sorted(found)


_NON_CODE_DIRS = {"tests", "test", "evals", "references", "assets", "templates",
                  "node_modules", ".venv", "venv", "site-packages", "__pycache__",
                  ".git", "dist", "build"}


def _any_code_anywhere(skill_dir: Path) -> list[str]:
    """Every non-test source file ANYWHERE in the skill, not just `scripts/`.

    `_code_files` deliberately looks only at `scripts/` and the skill root, which
    is the right scope for "what must steps 2-3 syntax-check and test". It is the
    WRONG scope for adjudicating `latent_only`, because that flag is a claim
    about the whole skill: with `_code_files` alone, `latent_only: true` plus
    `src/core.py` classifies as purely latent, steps 2 and 3 SKIP, and the code
    ships entirely ungated. Deciding a whole-skill claim needs a whole-skill scan.
    """
    out = []
    for p in skill_dir.rglob("*"):
        if not p.is_file() or p.suffix not in CODE_EXTS:
            continue
        rel = p.relative_to(skill_dir)
        if _NON_CODE_DIRS.intersection(rel.parts[:-1]):
            continue
        if _is_test_file(p.name) or p.name in {"__init__.py", "conftest.py", "setup.py"}:
            continue
        out.append(str(rel))
    return sorted(out)


def _test_files(skill_dir: Path, kind: str = "") -> list[str]:
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
    if path.suffix == ".py":
        try:
            tree = ast.parse(txt)
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
    if path.suffix == ".sh":
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
    "should_trigger", "should_not_trigger", "shouldTrigger",
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

    if path.suffix == ".json":
        try:
            return _walk_for_trigger_keys(json.loads(txt))
        except (json.JSONDecodeError, RecursionError):
            return False
    if path.suffix in {".yaml", ".yml"}:
        if yaml is not None:
            try:
                return _walk_for_trigger_keys(yaml.safe_load(txt))
            except Exception:
                return False
        # No PyYAML: fall through to the regex rather than silently reporting
        # "no trigger eval" for a file we simply could not parse.
    if path.suffix in _EVAL_DATA_EXTS - {".json", ".yaml", ".yml"}:
        return len(_textual_polarities(txt)) >= 2
    return len(_textual_polarities(_strip_code_noise(txt))) >= 2


# Keys whose boolean value states the polarity directly, vs. inverted ("this
# prompt must NOT fire the skill" is a negative case when the value is true).
_POSITIVE_KEYS = {"should_trigger", "shouldTrigger", "should_fire"}
_NEGATIVE_KEYS = {"should_not_trigger", "should_not_fire", "negative_case"}

# Textual analogue of _trigger_polarities, for code/markdown eval suites that
# cannot be parsed structurally. Requires a boolean LITERAL on the key — a bare
# `should_trigger:` mention asserts nothing.
# ONE pass, then classify. Two overlapping regexes let a single line match both
# and supply both polarities by itself — first `should_trigger = "false"`, then
# `should_trigger = "false prompt"` once the exclusion only covered exact
# literals. Chasing that with ever-more-precise lookaheads is unbounded; matching
# the value ONCE and classifying it exclusively removes the class.
_TRIGGER_ASSERTION_ANY_RE = re.compile(
    r"[\"']?(" + "|".join(sorted(TRIGGER_ASSERTION_KEYS)) + r")[\"']?\s*[:=]\s*"
    r"(\[\s*[^\]\s][^\]]*\]|\[\s*\]|\n\s*-\s*\S|[\"'][^\"']*[\"']|[A-Za-z0-9_.+-]+)", re.I)
_BOOL_LITERAL_RE = re.compile(r"^[\"']?(true|false)[\"']?$", re.I)


def _textual_polarities(txt: str) -> set[bool]:
    """Polarities asserted by `key: value` pairs in unparsed text.

    Each match is classified into exactly one of three buckets:
      * a boolean literal  -> the VALUE carries the polarity
      * a real corpus      -> the KEY carries it (should_trigger: [prompts])
      * anything else      -> asserts nothing
    """
    out: set[bool] = set()
    for key, raw in _TRIGGER_ASSERTION_ANY_RE.findall(txt):
        positive = key in _POSITIVE_KEYS
        val = raw.strip()
        m = _BOOL_LITERAL_RE.match(val)
        if m:
            truthy = m.group(1).lower() == "true"
            out.add(truthy if positive else not truthy)
            continue
        # Corpus arm: a quoted string with real content, or a non-empty list/item.
        if val.startswith(("[", "-")):
            if val not in ("[]", "[ ]", "-"):
                out.add(positive)
        elif val[:1] in "\"'":
            if val.strip("\"'").strip():
                out.add(positive)
    return out


def _walk_for_trigger_keys(node: object, depth: int = 0) -> bool:
    """True iff the artifact asserts BOTH polarities with real boolean values.

    Key presence alone is not an assertion. `{"should_trigger": null}` names the
    concept and tests nothing, and once step 5 is REQUIRED for purely-latent
    skills such a token artifact would be the only thing standing between that
    skill and a green gate. A suite carrying one polarity is equally hollow: a
    positive-only set is satisfied by a skill that fires on everything, and a
    negative-only set by one that never fires at all. Demand both.
    """
    return len(_trigger_polarities(node)) >= 2


def _is_real_corpus(v: object) -> bool:
    """True for a prompt corpus that actually contains a prompt.

    `len(v) > 0` was too weak: `should_trigger: [null]` and `should_trigger: "  "`
    both have non-zero length and assert nothing, which is the same
    presence-not-content hole this check exists to close, one level down.
    """
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, tuple)):
        # A prompt is TEXT, or a case object carrying text. Accepting any
        # non-null scalar let `[false]` and `[0]` count as a prompt corpus — the
        # presence-not-content hole again, one level further down. Booleans and
        # numbers are not prompts, so enumerate what is rather than what isn't.
        return any(
            (isinstance(i, str) and i.strip())
            or (isinstance(i, dict) and any(
                isinstance(x, str) and x.strip() for x in i.values()))
            for i in v)
    return False


def _trigger_polarities(node: object, depth: int = 0) -> set[bool]:
    """The set of case polarities asserted anywhere in the structure.

    {True} = only positive cases, {False} = only negative, {True, False} = both.
    Non-boolean values (null, strings, numbers) assert nothing and are ignored.
    """
    out: set[bool] = set()
    if depth > 40:
        return out
    if isinstance(node, dict):
        for k, v in node.items():
            ks = str(k)
            polarity = (True if ks in _POSITIVE_KEYS
                        else False if ks in _NEGATIVE_KEYS else None)
            if polarity is not None:
                if isinstance(v, bool):
                    # Case-per-object schema: {"prompt": "...", "should_trigger": true}
                    out.add(v if polarity else not v)
                elif _is_real_corpus(v):
                    # Key-groups-prompts schema, equally valid and widely used:
                    #   should_trigger:      ["prompt a", "prompt b"]
                    #   should_not_trigger:  ["prompt c"]
                    # Here the KEY carries the polarity and the value is the corpus.
                    # Requiring a bool would report these real, two-polarity suites
                    # as asserting nothing.
                    out.add(polarity)
            out |= _trigger_polarities(v, depth + 1)
    elif isinstance(node, list):
        for v in node:
            out |= _trigger_polarities(v, depth + 1)
    return out


def _script_syntax_error(path: Path) -> str | None:
    """Return an error string if the script has a syntax error, else None.
    .mjs/.js/.ts checked only when `node` is present; otherwise not blocked."""
    if path.suffix == ".py":
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError:
            return "python syntax error"
        return None
    if path.suffix == ".sh":
        r = subprocess.run(["bash", "-n", str(path)], capture_output=True)
        return None if r.returncode == 0 else "shell syntax error"
    if path.suffix in (".mjs", ".js", ".ts") and shutil.which("node"):
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
    """Drop fenced code blocks — example commands and File-Structure trees inside
    them are not live contract claims. CommonMark allows tilde fences as well as
    backticks, and stripping only one kind leaves the other as a hiding place."""
    # CommonMark allows a fence to be indented up to 3 spaces; anchoring at
    # column zero left an indented fence as a hiding place.
    md = re.sub(r"^ {0,3}```.*?^ {0,3}```", "", md, flags=re.DOTALL | re.M)
    md = re.sub(r"```.*?```", "", md, flags=re.DOTALL)  # inline/unanchored leftovers
    return re.sub(r"^ {0,3}~~~.*?^ {0,3}~~~", "", md, flags=re.DOTALL | re.M)


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
        body = _strip_fences(md.read_text(encoding="utf-8", errors="replace"))
        for ln in body.splitlines():
            planned = bool(_PLANNED_RE.search(ln))
            for m in _REF_RE.finditer(ln):
                ref = m.group(1)
                if not planned and not _ref_satisfied(skill_dir, ref):
                    issues.append(f"SKILL.md → {ref} (missing; not marked planned)")
    sj = skill_dir / "skill.json"
    if sj.is_file():
        try:
            data = json.loads(sj.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            data = None
        ep = data.get("entrypoint") if isinstance(data, dict) else None
        if isinstance(ep, str) and ep and not _ref_satisfied(skill_dir, ep):
            issues.append(f"skill.json entrypoint → {ep} (missing)")

        def _walk(o, key=""):
            if isinstance(o, str):
                if key in _SKIP_JSON_KEYS or key == "entrypoint":
                    return  # entrypoint already checked explicitly above (no double-count)
                for m in _REF_RE.finditer(o):
                    ref = m.group(1)
                    if not _ref_satisfied(skill_dir, ref):
                        issues.append(f"skill.json → {ref} (missing)")
            elif isinstance(o, dict):
                for k, v in o.items():
                    _walk(v, k)
            elif isinstance(o, list):
                for v in o:
                    _walk(v, key)
        _walk(data)
    tdir = skill_dir / "templates"
    if tdir.is_dir():
        for y in sorted([*tdir.rglob("*.yaml"), *tdir.rglob("*.yml")]):
            for ln in y.read_text(encoding="utf-8", errors="replace").splitlines():
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


def run_checklist(skill_dir: Path, *, roles_dir: Path | None, registry: Path | None,
                  entities_dir: Path | None, strict: bool, run_tests: bool = False,
                  skills_sh: str | None = None) -> list[dict]:
    fm = parse_frontmatter(skill_dir / "SKILL.md")
    name = (fm or {}).get("name") or skill_dir.resolve().name
    latent_only = str((fm or {}).get("latent_only", "")).lower() in ("true", "yes", "1")
    code = _code_files(skill_dir)
    any_code = _any_code_anywhere(skill_dir)
    results: list[dict] = []

    def add(step, label, status, detail, required=False):
        results.append({"step": step, "label": label, "status": status,
                        "detail": detail, "required": required})

    # 1 — SKILL.md contract (required): frontmatter present + skills.sh-parseable
    # + VALID under the agentskills.io spec. The presence half of this check used
    # to be the whole of it, which made it satisfiable by construction: a
    # 2218-char description is truthy, so `kg` scored PASS at 2.2x the spec cap.
    # A presence check standing in for a validity check is green for the wrong
    # reason on every violation at once.
    gotcha = _skillsh_frontmatter_issue(skill_dir)
    type_issues = _frontmatter_type_issues(skill_dir / "SKILL.md")
    spec_issues = (type_issues + _spec_violations(fm)) if fm else type_issues
    if not (fm and fm.get("name") and fm.get("description")):
        add(1, "SKILL.md contract", FAIL,
            "SKILL.md missing" if fm is None else "frontmatter needs name + description", required=True)
    elif gotcha:
        add(1, "SKILL.md contract", FAIL,
            f"frontmatter breaks skills.sh parser (multi-quoted-string list item): {gotcha[:48]}", required=True)
    elif spec_issues:
        add(1, "SKILL.md contract", FAIL,
            "agentskills.io spec — " + "; ".join(spec_issues), required=True)
    else:
        add(1, "SKILL.md contract", PASS,
            f"name={fm['name']} ({len(fm['description'])}/{SPEC_MAX_DESCRIPTION} desc chars, "
            "spec-valid, skills.sh-parseable)", required=True)

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
            "every scripts/references/assets/templates reference resolves")

    # 1d — Trigger clarity (ADVISORY). The description is the ONLY surface the
    # model sees at startup, and it decides whether the skill ever runs. A
    # description that says what the skill DOES but never when to USE it leans on
    # the model to infer the trigger, and models undertrigger. Cheap deterministic
    # proxy: require an explicit when-clause.
    desc_text = (fm or {}).get("description") or ""
    # Strip negated clauses first so "NOT FOR: … do not use when X" cannot
    # satisfy a check about saying when the skill SHOULD fire.
    desc_affirmative = _WHEN_NEGATION_RE.sub(" ", desc_text)
    if not desc_text:
        add("1d", "Trigger clarity", SKIP, "no description to grade")
    elif _WHEN_CLAUSE_RE.search(desc_affirmative):
        add("1d", "Trigger clarity", PASS, "description carries an explicit when-clause")
    else:
        add("1d", "Trigger clarity", WARN,
            "description never says WHEN to use the skill (add 'USE WHEN: …' / "
            "'Triggers on …') — models undertrigger on what-only descriptions")

    # 1e — Gotchas (ADVISORY). The corrections you made by hand while doing the
    # task are the one part of a skill the model could not have generated itself;
    # without them the body decays into generic mush the model already knew.
    body = _body_after_frontmatter(skill_dir)
    # Fenced blocks are stripped (a heading inside ``` is sample text, not a
    # section) and a heading that NEGATES the section — "## No gotchas" — must
    # not satisfy a check that the corrections were written down.
    body_prose = _strip_fences(body)
    gotcha_hit = next(
        (m for m in _GOTCHA_SECTION_RE.finditer(body_prose)
         if not _NEGATED_HEADING_RE.search(
             m.group(0)[:m.group(0).lower().find(m.group(1).lower())])),
        None)
    if gotcha_hit:
        add("1e", "Gotchas section", PASS, "body carries a gotchas/pitfalls/anti-rationalization section")
    else:
        add("1e", "Gotchas section", WARN,
            "no gotchas/pitfalls/anti-rationalization section — record the corrections "
            "you made by hand, or the next agent repeats them")

    # 1f — Body budget (ADVISORY, never gates). Per-trigger dilution, not standing
    # cost: unlike the description this loads only when the skill fires, so it is
    # deliberately a WARN even though an over-long body measurably degrades the
    # skill's own performance when it does fire.
    body_lines = len(body.splitlines())
    if body_lines > SPEC_RECOMMENDED_BODY_LINES:
        add("1f", "Body budget", WARN,
            f"{body_lines} lines > {SPEC_RECOMMENDED_BODY_LINES} recommended — "
            "split detail into references/ (progressive disclosure)")
    else:
        add("1f", "Body budget", PASS, f"{body_lines}/{SPEC_RECOMMENDED_BODY_LINES} lines")

    # 2 — Deterministic code: present + SYNTAX-VALID (required unless truly latent)
    # The latent_only contradiction is adjudicated against the WHOLE skill, not
    # just scripts/: otherwise code parked in src/ or lib/ makes the claim true
    # by construction and steps 2+3 go blind on real code.
    if latent_only and any_code:
        add(2, "Deterministic code", FAIL,
            f"latent_only:true but {len(any_code)} source file(s) present "
            f"({', '.join(any_code[:3])}) — contradiction", required=True)
    elif latent_only:
        add(2, "Deterministic code", SKIP, "latent_only: true — composition skill, no scripts")
    elif code:
        broken = [(c, e) for c in code if (e := _script_syntax_error(skill_dir / c))]
        if broken:
            add(2, "Deterministic code", FAIL,
                "; ".join(f"{c}: {e}" for c, e in broken[:3]), required=True)
        else:
            add(2, "Deterministic code", PASS,
                f"{len(code)} script(s), syntax ok: {', '.join(code[:3])}", required=True)
    else:
        add(2, "Deterministic code", FAIL,
            "no scripts/ code (set latent_only: true for a pure composition skill)", required=True)

    # 3 — Unit tests: present + REAL (non-empty, test construct) [+ run if asked]
    require_tests = bool(code) and not latent_only or (latent_only and code)
    all_tests = _test_files(skill_dir)
    real_tests = [t for t in all_tests if _is_real_test(skill_dir / t)]
    if not require_tests:
        add(3, "Unit tests", SKIP if not real_tests else PASS,
            "no code to test" if not real_tests else f"{len(real_tests)} test file(s)")
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
    # REQUIRED for a purely-latent skill. `latent_only: true` with no scripts
    # makes steps 2 and 3 SKIP ("no code to test"), so while this stayed advisory
    # such a skill could pass the whole gate with ZERO required assertions about
    # its behaviour. That inverts the risk exactly: a latent_only skill is not the
    # low-risk case, it is the case where 100% of the behaviour is latent and the
    # trigger eval is the only instrument that exists. Requiring tests only where
    # scripts exist waives evals precisely where behaviour is unobservable.
    eval_files = _eval_files(skill_dir)
    trigger_evals = [f for f in eval_files if _is_trigger_eval(skill_dir / f)]
    purely_latent = bool(latent_only) and not any_code
    if trigger_evals:
        add(5, "LLM evals", PASS,
            f"{len(trigger_evals)} trigger eval(s): {', '.join(trigger_evals[:3])}",
            required=purely_latent)
    elif eval_files:
        add(5, "LLM evals", FAIL if purely_latent else WARN,
            f"{len(eval_files)} eval artifact(s) but none assert trigger behaviour "
            f"({'/'.join(sorted(TRIGGER_ASSERTION_KEYS)[:3])}…) — latent half still ungated"
            + (" and this skill is ALL latent half (latent_only, no scripts)" if purely_latent else ""),
            required=purely_latent)
    else:
        add(5, "LLM evals", FAIL if purely_latent else WARN,
            "no trigger eval and the skill is all latent half (latent_only, no scripts) — "
            "steps 2+3 cannot see it, so this is the only gate on its behaviour"
            if purely_latent else "none (recommended for judgment-output skills)",
            required=purely_latent)

    # 6 — Resolver trigger (workspace-aware; under --strict the missing path is
    # itself a FAIL — strict must not pass while skipping the checks it exists for)
    if registry is None:
        add(6, "Resolver trigger", FAIL if strict else SKIP,
            "(--strict) requires --registry <roles/_index.md|AGENTS.md>" if strict
            else "pass --registry <roles/_index.md> to check", required=strict)
    else:
        add(6, "Resolver trigger", *(_check_registry(registry, name)), required=strict)

    # 7 — Resolver eval (workspace-aware; missing path FAILs under --strict)
    if roles_dir is None:
        add(7, "Resolver eval", FAIL if strict else SKIP,
            "(--strict) requires --roles-dir" if strict else "pass --roles-dir to check", required=strict)
    else:
        evalf = roles_dir / f"{name}.eval.yaml"
        ok = evalf.is_file()
        add(7, "Resolver eval", PASS if ok else (FAIL if strict else WARN),
            f"{evalf.name} present" if ok else f"no {name}.eval.yaml (skillify step 7)", required=strict)

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
            re.search(rf"\b{re.escape(name)}\b", p.read_text(encoding="utf-8", errors="replace"))
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
    for raw in registry.read_text(encoding="utf-8", errors="replace").splitlines():
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="skillify-check",
        description="Run the 10-step skillify readiness checklist on a skill directory.")
    ap.add_argument("skill_dir", help="path to the skill directory (contains SKILL.md)")
    ap.add_argument("--roles-dir", default=None, help="workspace roles/ dir (enables step 7)")
    ap.add_argument("--registry", default=None, help="AGENTS.md or registry file (enables step 6)")
    ap.add_argument("--entities-dir", default=None, help="research/entities dir (enables step 10)")
    ap.add_argument("--strict", action="store_true", help="require steps 6+7 (and fail if their path flag is missing)")
    ap.add_argument("--run-tests", action="store_true", help="actually run pytest for step 3 (not just detect)")
    ap.add_argument("--skills-sh", default=None, metavar="REPO_OR_PATH",
                    help="step 9: run `npx skills add <REPO_OR_PATH> --list` and require the skill is listed (real skills.sh install-verify)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    skill_dir = Path(args.skill_dir)
    if not skill_dir.is_dir():
        print(f"[skillify] not a directory: {skill_dir}", file=sys.stderr)
        return 2

    results = run_checklist(
        skill_dir,
        roles_dir=Path(args.roles_dir) if args.roles_dir else None,
        registry=Path(args.registry) if args.registry else None,
        entities_dir=Path(args.entities_dir) if args.entities_dir else None,
        strict=args.strict, run_tests=args.run_tests, skills_sh=args.skills_sh)

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
