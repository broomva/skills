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
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        return None
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
            fm[key.strip()] = val.strip().strip("\"'")
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
    """Drop fenced code blocks (``` … ```) — example commands and File-Structure
    trees inside them are not live contract claims."""
    return re.sub(r"```.*?```", "", md, flags=re.DOTALL)


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


def _model_family(model: str) -> str | None:
    m = (model or "").lower()
    for fam, toks in _MODEL_FAMILIES.items():
        if any(t in m for t in toks):
            return fam
    return None


def _load_data(path: Path) -> object | None:
    """Parse a JSON/YAML artifact, or None if unreadable/unparseable."""
    try:
        txt = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if path.suffix == ".json":
        try:
            return json.loads(txt)
        except ValueError:
            return None
    if path.suffix in {".yaml", ".yml"} and yaml is not None:
        try:
            return yaml.safe_load(txt)
        except Exception:
            return None
    return None


def _eval_blobs(skill_dir: Path) -> list[tuple[Path, dict]]:
    """Every parseable mapping under evals/ — where J's declarations may live."""
    out: list[tuple[Path, dict]] = []
    d = skill_dir / "evals"
    if not d.is_dir():
        return out
    for f in sorted(d.rglob("*")):
        if not f.is_file() or f.suffix not in {".json", ".yaml", ".yml"}:
            continue
        data = _load_data(f)
        if isinstance(data, dict):
            out.append((f, data))
    return out


def _dig(blobs: list[tuple[Path, dict]], key: str) -> object | None:
    """First top-level value for `key` across the eval blobs."""
    for _, data in blobs:
        if key in data:
            return data[key]
    return None


_ADMITTED_RE = re.compile(r"^\s*(?:[-*>#\s]*)?\**\s*(?:outcome|verdict|result)\s*\**\s*[:\-]\s*\**\s*(admitted|rejected)\b",
                          re.IGNORECASE | re.MULTILINE)


def _admission_issue(skill_dir: Path) -> str | None:
    """Tier J's hard gate. `evals/admission.md` must record the admission test AND
    its outcome: given the same input, can two independent agents produce outputs a
    third party judges BOTH valid? If they contradict with no tiebreak the skill is
    underspecified, not probabilistic, and is not admissible.

    A file with no explicit outcome line is NOT admitted — an unrecorded admission
    test is an unadmitted skill, and treating 'the file exists' as the outcome is the
    presence-is-not-correctness trap this whole gate is built against.
    """
    f = skill_dir / "evals" / "admission.md"
    if not f.is_file():
        return "no evals/admission.md (record the admission test and its outcome)"
    txt = f.read_text(encoding="utf-8", errors="replace")
    if not txt.strip():
        return "evals/admission.md is empty"
    m = _ADMITTED_RE.search(txt)
    if not m:
        return ("evals/admission.md records no outcome — needs a line like "
                "`Outcome: admitted` (or `rejected`)")
    if m.group(1).lower() == "rejected":
        return "evals/admission.md records `rejected` — an underspecified skill is not admissible"
    return None


def _held_out_count(skill_dir: Path, blobs: list[tuple[Path, dict]]) -> int:
    """Held-out cases: a dedicated evals/held-out/ dir, or cases flagged held_out."""
    d = skill_dir / "evals" / "held-out"
    n = len([f for f in d.rglob("*") if f.is_file()]) if d.is_dir() else 0
    for _, data in blobs:
        cases = data.get("cases")
        if isinstance(cases, list):
            n += sum(1 for c in cases if isinstance(c, dict)
                     and str(c.get("held_out", "")).lower() in ("true", "yes", "1"))
    return n


def _judge_issues(skill_dir: Path, blobs: list[tuple[Path, dict]]) -> tuple[list[str], list[str]]:
    """Validate tier J's judge declaration. Returns (failures, warnings).

    Required: a `judge` mapping with a `model`; that model must DIFFER from the model
    under eval (cross-model is structural for J — a judge sharing the generator's
    substrate inflates confidence rather than testing it); and an
    `agreement_floor` that is accompanied by an `agreement_measured` record.

    The floor's VALUE is deliberately not constrained here. Nobody has measured what
    it should be, and hard-coding one would be asserting a number no committed process
    regenerates — the exact failure that produced this tier model. The gate enforces
    the shape: declare a floor, and show the measurement that produced it.
    """
    fails: list[str] = []
    warns: list[str] = []
    judge = _dig(blobs, "judge")
    if not isinstance(judge, dict):
        return ["no `judge` config in evals/ (tier J needs a cross-model judge declaration)"], warns

    jm = judge.get("model")
    if not isinstance(jm, str) or not jm.strip():
        fails.append("judge.model missing")
        jm = ""

    # the model under eval: skill_evals' execution_contract.model, else the harness default
    under = ""
    ec = _dig(blobs, "execution_contract")
    if isinstance(ec, dict) and isinstance(ec.get("model"), str):
        under = ec["model"]
    if jm and under:
        if jm.strip().lower() == under.strip().lower():
            fails.append(f"judge.model == model under eval ({jm!r}) — self-judging is not a gate")
        elif _model_family(jm) and _model_family(jm) == _model_family(under):
            warns.append(f"judge.model {jm!r} and model-under-eval {under!r} share a family "
                         f"({_model_family(jm)}) — distinct names, correlated substrate")
    elif jm and not under:
        warns.append("no execution_contract.model to compare judge.model against — "
                     "cross-model distinctness unverified")

    floor = judge.get("agreement_floor")
    measured = judge.get("agreement_measured")
    if floor is None:
        fails.append("judge.agreement_floor not declared")
    elif not isinstance(measured, dict) or not measured.get("value") or not measured.get("method"):
        fails.append(f"judge.agreement_floor={floor} declared with no agreement_measured "
                     "{value, method} — an unmeasured floor is an authored number")
    return fails, warns


def _tier_of(skill_dir: Path, fm: dict, code: list[str],
             blobs: list[tuple[Path, dict]]) -> tuple[str | None, bool, str]:
    """Return (tier, declared, why). Declared wins; otherwise infer.

    Inference exists so a 94-skill roster does not break the day tiers ship — NOT to
    let an unclassifiable skill through. `None` means the gate could not tell what
    kind of thing this is, and that is a FAIL, same as before.
    """
    raw = str(fm.get("tier", "")).strip().upper()
    if raw in TIERS:
        return raw, True, "declared"
    if raw:
        return None, False, f"tier: {raw!r} is not one of D/J/L"
    # Inference fires for D ONLY. Shipping a pure function is definitionally tier D,
    # so that one is safe. The tempting second rule — "has a trigger eval, no code
    # -> L" — is NOT: a routing eval is tier L's *core*, not its *signature*, and
    # every tier can carry one. Backfilling the roster with that rule labelled
    # `autonomous`, `handoff` and `checkit` as lenses; all three run pipelines and
    # none of them is a lens. A confidently wrong tier is worse than an absent one,
    # because it makes the taxonomy look like it carves when it does not (BRO-2192).
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
    blobs = _eval_blobs(skill_dir)
    tier, tier_declared, tier_why = _tier_of(skill_dir, fm or {}, code, blobs)
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
            "every scripts/references/assets/templates reference resolves")

    # 2 — Tier + its core (required). The gate no longer asks the single question
    # "is there a deterministic core?" — that let a testability question decide an
    # expressibility question, and it gated NOTHING on the `latent_only` branch.
    # Step 2 now asks what KIND of skill this is and applies that tier's gate.
    # Inference picks WHICH gate when `tier:` is absent; it never waives one.
    tag = "tier " + (tier or "?") + (" (declared)" if tier_declared else f" ({tier_why})")
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
    elif tier == TIER_D:
        if not code:
            add(2, "Tier + core", FAIL, "tier D declared but no scripts/ code", required=True)
        elif (broken := [(c, e) for c in code if (e := _script_syntax_error(skill_dir / c))]):
            add(2, "Tier + core", FAIL,
                f"{tag}: " + "; ".join(f"{c}: {e}" for c, e in broken[:3]), required=True)
        else:
            add(2, "Tier + core", PASS,
                f"{tag}: {len(code)} script(s), syntax ok: {', '.join(code[:3])}", required=True)
    elif tier == TIER_J:
        issues: list[str] = []
        if (adm := _admission_issue(skill_dir)):
            issues.append(adm)
        if not (_dig(blobs, "rubric") or (skill_dir / "evals" / "rubric.md").is_file()):
            issues.append("no rubric (evals/rubric.md or a `rubric` key in evals/)")
        if (n_held := _held_out_count(skill_dir, blobs)) == 0:
            issues.append("no held-out cases (evals/held-out/ or cases flagged held_out)")
        jf, jw = _judge_issues(skill_dir, blobs)
        issues += jf
        for w in jw:
            add("2j", "Judge distinctness", WARN, w)
        if issues:
            shown = "; ".join(issues[:3]) + ("; …" if len(issues) > 3 else "")
            add(2, "Tier + core", FAIL, f"{tag}: {len(issues)} gap(s): {shown}", required=True)
        else:
            add(2, "Tier + core", PASS,
                f"{tag}: admission recorded, rubric + {n_held} held-out case(s), "
                "cross-model judge with a measured floor", required=True)
        # The judge itself is an unbuilt seam. Reporting its RUN as a PASS because the
        # artifacts exist would be exactly the vacuous pass this harness exists to
        # prevent, so it is a named SKIP either way.
        add("2j*", "Judge execution", SKIP,
            "LLM judge is a declared seam — skill_evals/checks.py:make_judge_check "
            "raises rather than stubbing a pass; tier J gates artifacts, not judged output")
    else:  # TIER_L
        trig = [f for f in _eval_files(skill_dir) if _is_trigger_eval(skill_dir / f)]
        if trig:
            add(2, "Tier + core", PASS,
                f"{tag}: {len(trig)} routing eval(s): {', '.join(trig[:2])}", required=True)
        else:
            add(2, "Tier + core", FAIL,
                f"{tag}: no routing eval — a lens is gated on firing on the right requests "
                "and staying silent on near-misses", required=True)
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
        fm = parse_frontmatter(md) or {}
        code = _code_files(d)
        blobs = _eval_blobs(d)
        tier, declared, why = _tier_of(d, fm, code, blobs)
        res = run_checklist(d, **kw)
        failed = [r for r in res if r["required"] and r["status"] != PASS]
        rows.append({
            "skill": fm.get("name") or d.name,
            "path": str(d.relative_to(root)) if d.is_relative_to(root) else str(d),
            "tier": tier, "declared": declared, "why": why,
            "failed": [f"{r['step']} {r['label']}" for r in failed],
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
