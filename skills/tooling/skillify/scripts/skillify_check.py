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
  (declaring it while shipping scripts is a contradiction → FAIL).

Required steps gate the exit code: 1 (SKILL.md contract), 2 (code syntax — unless
genuinely latent), 3 (real unit tests, when code present). Workspace-aware steps
(6 resolver trigger, 7 resolver eval, 10 brain filing) SKIP unless their path
flag is supplied. `--strict` promotes 6/7 to required *and* fails if their path
flag is missing (so strict can't pass while skipping the things strict is for).

Pure-stdlib + optional pyyaml/node; deterministic; zero network.
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

CODE_EXTS = {".py", ".sh", ".mjs", ".js", ".ts"}
_TEST_CODE_EXTS = ("py", "sh", "mjs", "js", "ts")
PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"


# --- frontmatter -------------------------------------------------------------

def parse_frontmatter(md_path: Path) -> dict | None:
    """Return the top YAML frontmatter as a flat str dict, or None if absent.

    Uses pyyaml when available (correctly handles folded/block scalars like
    `description: >-`); falls back to a scalar-only hand-roll that skips
    indented continuation lines so folded prose can't manufacture bogus keys.
    """
    try:
        # errors="replace": invalid UTF-8 must fail CLOSED (no frontmatter -> step 1
        # FAIL), never raise. A single 0xFF byte in one SKILL.md used to abort the
        # whole --survey run with a UnicodeDecodeError.
        text = md_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    text = text.lstrip("\ufeff")  # a BOM made the ^--- match fail, hiding frontmatter
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
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
            val = val.strip()
            if not val.startswith(("\"", "'")):
                # YAML: " #" begins a comment on a plain scalar. Without this the
                # template documented in this very skill — `outcome: admitted
                # # or: rejected` — parsed as the literal 'admitted # or: rejected'
                # on any machine without pyyaml.
                val = re.split(r"\s+#", val, 1)[0].strip()
            fm[key.strip()] = val.strip("\"'")
    return fm


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
    is_py = path.suffix == ".py" or (m and m.group(1).lower() in _PY_INTERPRETERS)
    if is_py:
        try:
            body = ast.parse(txt).body
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


def _is_code_file(skill_dir: Path, f: Path) -> bool:
    """Code = a recognized extension, OR an extensionless EXECUTABLE under scripts/.
    `scripts/run` with a shebang is a deterministic core by any reading; keying purely
    off five suffixes let it ship untested ("tests whenever code ships" quietly meant
    "whenever a .py/.sh/.mjs/.js/.ts ships")."""
    if _is_test_file(f.name) or f.name in {"__init__.py", "conftest.py", "setup.py"}:
        return False
    if f.suffix in CODE_EXTS:
        return True
    return (not f.suffix and f.is_relative_to(skill_dir / "scripts")
            and bool(f.stat().st_mode & 0o111))


def _code_files(skill_dir: Path) -> list[str]:
    found = set()
    for f in _iter_files(skill_dir, ("scripts", "")):
        try:
            if _is_code_file(skill_dir, f):
                found.add(str(f.relative_to(skill_dir)))
        except OSError:
            continue
    return sorted(found)


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
        return bool(_TRIGGER_ASSERTION_RE.search(txt))
    return bool(_TRIGGER_ASSERTION_RE.search(_strip_code_noise(txt)))


def _walk_for_trigger_keys(node: object, depth: int = 0) -> bool:
    """A trigger key must appear as an actual mapping KEY, at any nesting depth."""
    if depth > 40:
        return False
    if isinstance(node, dict):
        if TRIGGER_ASSERTION_KEYS & set(map(str, node.keys())):
            return True
        return any(_walk_for_trigger_keys(v, depth + 1) for v in node.values())
    if isinstance(node, list):
        return any(_walk_for_trigger_keys(v, depth + 1) for v in node)
    return False


def _syntax_checkable(path: Path) -> bool:
    """Whether this build can actually syntax-check the file. Used so the PASS line
    never claims `syntax ok` about something nothing examined."""
    if path.suffix in (".py", ".sh"):
        return True
    if path.suffix in (".mjs", ".js", ".ts"):
        return bool(shutil.which("node"))
    if not path.suffix:
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
    if not path.suffix:
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
            ast.parse(_read(path) or "")
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
            data = json.loads(sj.read_text(encoding="utf-8", errors="replace"))
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


def _substantive(x: object) -> bool:
    """Structural presence only: a finite number, or a non-empty string.

    This used to try to detect placeholder CONTENT — "TBD", "vibes", "n/a" — and it was
    rebuilt five times. Every rebuild produced a fresh crop of FALSE REJECTS on honest
    prose: "Write me a concise incident report from these logs.", "excluded 3 cases
    with unknown labels", "Unknown cause.", "TBD is not an acceptable answer; explain
    why." Each fix bought one shape and broke another, because the question it asked —
    is this text evasive or descriptive? — is the same undecidable question as "is this
    measurement real?", which SKILL.md already declares out of scope.

    So it is gone. A field that is present and non-empty passes; whether its contents
    mean anything is the review layer's job, which is where that judgement was always
    going to have to live. Deleting the heuristic removed eight false-reject classes at
    once, along with about eighty lines of regex.
    """
    if isinstance(x, bool):
        return False
    if isinstance(x, (int, float)):
        return math.isfinite(x)
    return isinstance(x, str) and bool(x.strip())


def _read(path: Path) -> str | None:
    """Read text, or None if unreadable. Every caller must fail CLOSED on None — an
    unreadable artifact is an unverified artifact, never a traceback."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


class _Unparseable:
    """Sentinel: the file exists but this build cannot parse it (no pyyaml). Distinct
    from 'absent', so the gate can say which — reporting a correct YAML judge config as
    `no judge config` was a real misdiagnosis in review."""
    __slots__ = ("path",)

    def __init__(self, path: Path):
        self.path = path


def _load_data(path: Path) -> object | None | _Unparseable:
    """Parse a JSON/YAML artifact. None = absent/empty; _Unparseable = cannot verify."""
    txt = _read(path)
    if txt is None:
        return _Unparseable(path)  # unreadable is UNVERIFIED, not absent
    if not txt.strip():
        return None
    if path.suffix == ".json":
        try:
            return json.loads(txt)
        except ValueError:
            return _Unparseable(path)
    if path.suffix in {".yaml", ".yml"}:
        if yaml is None:
            return _Unparseable(path)
        try:
            return yaml.safe_load(txt)
        except Exception:
            return _Unparseable(path)
    return None


def _eval_blobs(skill_dir: Path) -> tuple[list[tuple[Path, dict]], list[Path]]:
    """Every parseable mapping under evals/, plus the files that could not be parsed.

    The unparseable list is returned rather than swallowed: a J skill whose judge
    config is a YAML file this build cannot read must FAIL saying so, not FAIL saying
    the config is missing, and must never PASS by the file being invisible.
    """
    out: list[tuple[Path, dict]] = []
    bad: list[Path] = []
    d = skill_dir / "evals"
    if not d.is_dir():
        return out, bad
    for f in sorted(d.rglob("*")):
        if not f.is_file() or f.suffix not in {".json", ".yaml", ".yml"}:
            continue
        data = _load_data(f)
        if isinstance(data, _Unparseable):
            bad.append(f)
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
    f = skill_dir / "evals" / "admission.md"
    if not f.is_file():
        return ("no evals/admission.md — record the admission test and declare its "
                f"outcome in frontmatter:\n{_ADMISSION_TEMPLATE}")
    raw = _read(f)
    if raw is None:
        return "evals/admission.md is unreadable"
    fm = parse_frontmatter(f) or {}
    # Case-insensitive KEY lookup: the value was already compared case-insensitively,
    # so `Outcome: admitted` failing with "declares no outcome" was an undocumented
    # asymmetry that reads as the gate not seeing what is plainly there.
    raw_outcome = next((v for k, v in fm.items() if str(k).strip().lower() == "outcome"), "")
    outcome = str(raw_outcome).strip().lower()
    if not outcome:
        return ("evals/admission.md declares no `outcome` in frontmatter — add:\n"
                f"{_ADMISSION_TEMPLATE}")
    if outcome in ("", "none", "null"):
        return ("evals/admission.md declares an empty `outcome` — set it to `admitted` "
                "or `rejected`")
    if outcome not in ("admitted", "rejected"):
        return f"evals/admission.md outcome: {outcome!r} — must be `admitted` or `rejected`"
    if outcome == "rejected":
        return ("evals/admission.md declares `outcome: rejected` — an underspecified "
                "skill is not admissible")
    m = re.match(r"^\ufeff?---\n(.*?)\n---[^\S\n]*(?:\n|$)", raw, re.DOTALL)
    block = m.group(1) if m else ""
    declared = re.findall(r"(?m)^outcome\s*:", block)
    if len(declared) > 1:
        return (f"evals/admission.md declares `outcome` {len(declared)} times — "
                "contradictory declarations; keep exactly one")
    body = raw[m.end():] if m else ""
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
            if not f.is_file() or f.name.startswith(".") or f.suffix not in _CASE_EXTS:
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
_NEGATIVE_KEYS = {"should_not_trigger", "should_not_fire", "negative_case"}


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
        if isinstance(v, list) and v:
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
                        unparseable: list[Path]) -> str | None:
    """Tier L's core: a routing eval asserting BOTH polarities. A positive-only suite
    structurally cannot see over-triggering, which is the failure mode a lens has."""
    if unparseable:
        return (f"{len(unparseable)} eval artifact(s) could not be parsed "
                f"({unparseable[0].name}) — install pyyaml or fix the file; "
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


def _tier_of(skill_dir: Path, fm: dict, code: list[str]) -> tuple[str | None, bool, str]:
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
    raw = fm.get("tier")
    raw = "" if raw is None else str(raw).strip().upper()
    if raw in TIERS:
        return raw, True, "declared"
    if raw:
        return None, False, f"tier: {raw!r} is not one of D/J/L"
    if code:
        return TIER_D, False, "inferred: ships scripts/ code"
    return None, False, "no tier: declared and no scripts/ code (J and L must be declared)"


def run_checklist(skill_dir: Path, *, roles_dir: Path | None, registry: Path | None,
                  entities_dir: Path | None, strict: bool, run_tests: bool = False,
                  skills_sh: str | None = None) -> list[dict]:
    fm = parse_frontmatter(skill_dir / "SKILL.md")
    name = (fm or {}).get("name") or skill_dir.resolve().name
    latent_only = str((fm or {}).get("latent_only", "")).lower() in ("true", "yes", "1")
    code = _code_files(skill_dir)
    blobs, unparseable_evals = _eval_blobs(skill_dir)
    tier, tier_declared, tier_why = _tier_of(skill_dir, fm or {}, code)
    results: list[dict] = []

    def add(step, label, status, detail, required=False):
        results.append({"step": step, "label": label, "status": status,
                        "detail": detail, "required": required})

    # 1 — SKILL.md contract (required): frontmatter present + skills.sh-parseable.
    gotcha = _skillsh_frontmatter_issue(skill_dir)
    if not (fm and fm.get("name") and fm.get("description")):
        add(1, "SKILL.md contract", FAIL,
            "SKILL.md missing" if fm is None else "frontmatter needs name + description", required=True)
    elif gotcha:
        add(1, "SKILL.md contract", FAIL,
            f"frontmatter breaks skills.sh parser (multi-quoted-string list item): {gotcha[:48]}", required=True)
    else:
        add(1, "SKILL.md contract", PASS, f"name={fm['name']} (skills.sh-parseable)", required=True)

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
    empty_code = [c for c in code if not _has_executable_content(skill_dir / c)]

    if tier is None:
        add(2, "Tier + core", FAIL,
            f"cannot classify — {tier_why}. Declare `tier: D` (ship scripts/), "
            "`tier: J` (ship evals/admission.md + rubric + held-out cases + judge config), "
            "or `tier: L` (ship a both-polarity routing eval). If this skill is a "
            "PROCEDURE binding an external capability (a CLI, an API, a hosted runtime) "
            "it is none of the three — that residue is BRO-2192, and until it lands the "
            "honest options are an integration test (step 4) or an explicit tier", required=True)
    elif latent_only and code:
        add(2, "Tier + core", FAIL,
            f"latent_only:true but {len(code)} script(s) present — contradiction", required=True)
    elif broken:
        add(2, "Tier + core", FAIL,
            f"{tag}: " + "; ".join(f"{c}: {e}" for c, e in broken[:3]), required=True)
    elif empty_code:
        # An empty file is not a deterministic core. py_compile is perfectly happy with
        # 0 bytes, so `touch scripts/noop.py` used to satisfy tier D.
        add(2, "Tier + core", FAIL,
            f"{tag}: empty script(s) {', '.join(empty_code[:3])} — an empty file is not a core",
            required=True)
    elif tier == TIER_D:
        if not code:
            add(2, "Tier + core", FAIL, "tier D declared but no scripts/ code", required=True)
        else:
            checked = [c for c in code if _syntax_checkable(skill_dir / c)]
            claim = (f"{len(code)} script(s), syntax ok" if len(checked) == len(code)
                     else f"{len(code)} script(s), {len(checked)} syntax-checked "
                          f"({len(code) - len(checked)} unchecked: no checker for their type)")
            add(2, "Tier + core", PASS, f"{tag}: {claim}: {', '.join(code[:3])}", required=True)
    elif tier == TIER_J:
        issues: list[str] = []
        if unparseable_evals:
            issues.append(f"{len(unparseable_evals)} eval artifact(s) unparseable "
                          f"({unparseable_evals[0].name}) — install pyyaml or fix the file")
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
    require_tests = bool(code)
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
        if any(part in {"node_modules", ".git", "__pycache__", ".pytest_cache", ".worktrees"}
               for part in d.parts):
            continue
        # One odd file mode anywhere must not cost the whole report. This is the
        # command the docs tell a reader to run to regenerate the roster numbers;
        # an uncaught OSError two-thirds of the way through produced ZERO output.
        try:
            fm = parse_frontmatter(md) or {}
            code = _code_files(d)
            tier, declared, why = _tier_of(d, fm, code)
            res = run_checklist(d, **kw)
            failed = [f"{r['step']} {r['label']}" for r in res
                      if r["required"] and r["status"] != PASS]
        except Exception as exc:  # a skill that cannot be checked is not a skill that passed
            fm, tier, declared, why = {}, "errored", False, f"errored: {type(exc).__name__}"
            failed = [f"error: {type(exc).__name__}: {exc}"[:120]]
        rows.append({
            "skill": fm.get("name") or d.name,
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
