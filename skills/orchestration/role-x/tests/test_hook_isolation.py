"""A module committed to the session's repo must not reach the role-x hooks.

Both hooks run with the session's cwd. `python -c` puts that directory first on
sys.path and `python role-x.py` puts scripts/ first, so a yaml.py or json.py at
the repo root (or beside role-x.py) was imported in place of the real module and
ran as code on every prompt (BRO-2591 P20 r8). The hooks now launch every
interpreter with -I.

Pinned here, against the real hook scripts copied into a scratch plugin dir:
  - both polarities: with plants in the cwd and in scripts/, the hooks produce
    exactly the clean run's output, and no plant ever executes;
  - a positive control: a plant IS imported by a non-isolated interpreter, so
    the suite is not vacuous;
  - mutation: removing -I from any one site turns the suite red;
  - the user-site path: -I hides user site-packages, where PyYAML lives on the
    owner's machine. With an interpreter whose ONLY PyYAML is in its user site,
    both hooks must still work, and removing any one of the three re-adds must
    turn this red (without them, intake goes silent on every prompt).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
HOOKS = ("role-x-intake-hook.sh", "role-x-coverage-hook.sh")
PLANTS = ("json", "yaml", "argparse", "fnmatch", "hashlib", "subprocess",
          "datetime", "pathlib", "errno", "__future__", "typing")
SITE_RE = re.compile(r'"\$PYTHON_BIN" -I ')


def _seed_workspace(tmp: Path) -> Path:
    # Reuse the intake fixtures of the main suite, so this workspace is one the
    # rust lens actually scores against.
    import importlib.util

    spec = importlib.util.spec_from_file_location("_rx_main_tests", HERE / "test_role_x.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._seed_workspace(tmp)


def _plant(directory: Path, marks: Path) -> None:
    for name in PLANTS:
        (directory / f"{name}.py").write_text(
            f"open({str(marks / name)!r}, 'a').close()\nraise SystemExit(0)\n")


def _setup(tmp: Path, mutate: tuple[str, int] | None = None, planted: bool = False):
    plugin = tmp / "plugin" / "scripts"
    plugin.mkdir(parents=True)
    for f in (*HOOKS, "role-x.py"):
        shutil.copy2(SCRIPTS / f, plugin / f)
    if mutate:
        name, idx = mutate
        text = (plugin / name).read_text()
        m = list(SITE_RE.finditer(text))[idx]
        (plugin / name).write_text(text[:m.start()] + '"$PYTHON_BIN" ' + text[m.end():])
    ws = _seed_workspace(tmp)
    marks = tmp / "marks"
    marks.mkdir()
    if planted:
        _plant(ws, marks)
        _plant(plugin, marks)
    return plugin, ws, marks


def _run(plugin: Path, ws: Path, tmp: Path, hook: str, python: str | None = None,
         extra_env: dict | None = None) -> tuple[int, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env.update(extra_env or {})
    env.update({
        "ROLE_X_PYTHON": python or sys.executable,
        "CLAUDE_PROJECT_DIR": str(ws),
        "HOME": str(tmp / "home"),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    payload = '{"prompt": "fix the rust cargo build and the tokio async runtime", "session_id": "iso"}'
    p = subprocess.run(["bash", str(plugin / hook)], input=payload, capture_output=True,
                       text=True, cwd=ws, env=env, timeout=60)
    return p.returncode, p.stdout


def _outcomes(tmp: Path, mutate=None, planted=False):
    plugin, ws, marks = _setup(tmp, mutate, planted)
    out = {h: _run(plugin, ws, tmp, h) for h in HOOKS}
    return out, sorted(p.name for p in marks.iterdir())


def test_positive_control_plants_are_live(tmp_path):
    marks = tmp_path / "m"
    marks.mkdir()
    _plant(tmp_path, marks)
    subprocess.run([sys.executable, "-c", "import json"], cwd=tmp_path, capture_output=True)
    assert (marks / "json").exists(), "a planted json.py was not imported: the suite would be vacuous"


def test_intake_baseline_routes_a_lens(tmp_path):
    out, _ = _outcomes(tmp_path)
    rc, stdout = out["role-x-intake-hook.sh"]
    assert rc == 0
    assert "rust" in stdout, f"the clean intake run chose no lens, so nothing below is measured: {stdout!r}"


def test_plants_change_nothing_and_never_run(tmp_path):
    clean, _ = _outcomes(tmp_path / "clean")
    planted, marks = _outcomes(tmp_path / "planted", planted=True)
    assert marks == [], f"planted modules were imported: {marks}"
    assert planted == clean


def _sites():
    for hook in HOOKS:
        for i, _ in enumerate(SITE_RE.finditer((SCRIPTS / hook).read_text())):
            yield hook, i


def test_every_interpreter_launch_is_isolated():
    for hook in HOOKS:
        for n, line in enumerate((SCRIPTS / hook).read_text().splitlines(), 1):
            code = line.split("#", 1)[0]
            if '"$PYTHON_BIN" ' in code and "command -v" not in code:
                assert '"$PYTHON_BIN" -I ' in code, f"{hook}:{n} launches python without -I"
    assert len(list(_sites())) == 4


@pytest.mark.parametrize("site", list(_sites()), ids=lambda s: f"{s[0]}#{s[1]}")
def test_mutant_without_I_is_caught(tmp_path, site):
    _, marks = _outcomes(tmp_path, mutate=site, planted=True)
    assert marks, f"removing -I from {site} went unnoticed"


# ── the user-site path ──────────────────────────────────────────────────────

USERSITE_MUTANTS = [
    ("role-x-intake-hook.sh", "sys.path.append(site.getusersitepackages()); ", ""),
    ("role-x-coverage-hook.sh", "sys.path.append(site.getusersitepackages()); ", ""),
    ("role-x.py", "        sys.path.append(_user_site)\n", "        pass\n"),
]


@pytest.fixture(scope="module")
def usersite_python(tmp_path_factory):
    """An interpreter whose ONLY PyYAML is in its user site (the owner's Mac)."""
    import yaml

    root = tmp_path_factory.mktemp("usersite")
    venv = root / "venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True)
    vpy = str(venv / "bin" / "python")
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env["PYTHONUSERBASE"] = str(root / "userbase")
    site_dir = subprocess.run([vpy, "-I", "-c", "import site; print(site.getusersitepackages())"],
                              env=env, capture_output=True, text=True, check=True).stdout.strip()
    assert subprocess.run([vpy, "-I", "-c", "import yaml"], env=env,
                          capture_output=True).returncode != 0, "venv already has PyYAML: vacuous"
    Path(site_dir).mkdir(parents=True)
    shutil.copytree(Path(yaml.__file__).parent, Path(site_dir) / "yaml")
    return vpy, {"PYTHONUSERBASE": env["PYTHONUSERBASE"]}


def _usersite_outcome(tmp: Path, vpy: str, extra: dict, mutant=None):
    plugin, ws, _ = _setup(tmp)
    if mutant:
        name, old, new = mutant
        text = (plugin / name).read_text()
        assert text.count(old) == 1, (name, old)
        (plugin / name).write_text(text.replace(old, new))
    rc, out = _run(plugin, ws, tmp, "role-x-intake-hook.sh", vpy, extra)
    crc, _ = _run(plugin, ws, tmp, "role-x-coverage-hook.sh", vpy, extra)
    # The coverage hook prints nothing on a healthy registry; it touches its
    # cooldown stamp only once the PyYAML probe has passed.
    stamp = (tmp / "home" / ".config" / "broomva" / "role" / "coverage-stamp").exists()
    return rc, "rust" in out, crc, stamp


def test_user_site_pyyaml_still_routes(tmp_path, usersite_python):
    vpy, extra = usersite_python
    assert _usersite_outcome(tmp_path, vpy, extra) == (0, True, 0, True)


@pytest.mark.parametrize("mutant", USERSITE_MUTANTS, ids=lambda m: m[0])
def test_user_site_mutant_is_caught(tmp_path, usersite_python, mutant):
    vpy, extra = usersite_python
    got = _usersite_outcome(tmp_path, vpy, extra, mutant)
    assert got != (0, True, 0, True), f"removing the user-site re-add in {mutant[0]} went unnoticed"
    assert got[0] == 0 and got[2] == 0, f"a hook stopped failing open: {got}"


# ── reflex mode (ROLE_X_MODE=reflex) ────────────────────────────────────────
# role-x.py loads scripts/reflex_router.py by file path, and the router loads
# ctx-core's ctx.py the same way. Neither may pick a planted module from the
# session's cwd or from its own directory.

REFLEX_PLANTS = PLANTS + ("re", "dataclasses", "importlib", "time")


def _reflex_outcome(tmp: Path, planted: bool) -> tuple[int, str, list[str]]:
    plugin, ws, marks = _setup(tmp)
    shutil.copy2(SCRIPTS / "reflex_router.py", plugin / "reflex_router.py")
    (plugin.parent / "references").mkdir()
    shutil.copy2(SCRIPTS.parent / "references" / "reflexes.yaml", plugin.parent / "references")
    if planted:
        for d in (ws, plugin):
            for name in REFLEX_PLANTS:
                (d / f"{name}.py").write_text(
                    f"open({str(marks / name)!r}, 'a').close()\nraise SystemExit(0)\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env.update({"ROLE_X_PYTHON": sys.executable, "CLAUDE_PROJECT_DIR": str(ws),
                "HOME": str(tmp / "home"), "PYTHONDONTWRITEBYTECODE": "1", "ROLE_X_MODE": "reflex"})
    p = subprocess.run(["bash", str(plugin / "role-x-intake-hook.sh")],
                       input='{"prompt": "Merge 1857", "session_id": "iso"}',
                       capture_output=True, text=True, cwd=ws, env=env, timeout=60)
    return p.returncode, p.stdout, sorted(m.name for m in marks.iterdir())


def test_reflex_mode_plants_change_nothing_and_never_run(tmp_path):
    clean = _reflex_outcome(tmp_path / "clean", planted=False)
    assert clean[0] == 0 and "--match-head-commit" in clean[1], f"reflex baseline routed nothing: {clean}"
    planted = _reflex_outcome(tmp_path / "planted", planted=True)
    assert planted[2] == [], f"planted modules were imported: {planted[2]}"
    assert planted[:2] == clean[:2]
