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
    return bool(_JS_TEST_CONSTRUCT.search(_strip_code_noise(txt)))


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


def run_checklist(skill_dir: Path, *, roles_dir: Path | None, registry: Path | None,
                  entities_dir: Path | None, strict: bool, run_tests: bool = False,
                  skills_sh: str | None = None) -> list[dict]:
    fm = parse_frontmatter(skill_dir / "SKILL.md")
    name = (fm or {}).get("name") or skill_dir.resolve().name
    latent_only = str((fm or {}).get("latent_only", "")).lower() in ("true", "yes", "1")
    code = _code_files(skill_dir)
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

    # 2 — Deterministic code: present + SYNTAX-VALID (required unless truly latent)
    if latent_only and code:
        add(2, "Deterministic code", FAIL,
            f"latent_only:true but {len(code)} script(s) present — contradiction", required=True)
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

    # 5 — LLM evals (recommended)
    has_evals = bool(_test_files(skill_dir, "eval")) or (skill_dir / "evals").is_dir()
    add(5, "LLM evals", PASS if has_evals else WARN,
        "present" if has_evals else "none (recommended for judgment-output skills)", required=False)

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
