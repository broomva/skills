"""The skill's shape since BRO-3122: SKILL.md routes to workflow files that
exist, the CLI lists the same workflows, and the deprecated fleet-reconcile
alias still resolves (its SKILL.md, and scripts that forward here)."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
from conftest import SCRIPTS, SKILL

import fleet_reconcile

ALIAS = SKILL.parent / "fleet-reconcile"
#: A routing-table row: `| name | trigger | mechanism | [workflows/x.md](workflows/x.md) |`.
ROUTE = re.compile(r"^\| (\S+) \|.*\[(workflows/[^\]]+)\]\((workflows/[^)]+)\) \|\s*$")


def _frontmatter(path: Path) -> dict:
    """Top-level keys and block scalars, enough for these tests (no PyYAML in the CI deps)."""
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    out, key = {}, None
    for ln in text.split("\n---\n", 1)[0][4:].splitlines():
        m = re.match(r"^([a-z_]+):\s*(.*)$", ln)
        if m:
            key, val = m.group(1), m.group(2)
            out[key] = "" if val == "|" else val
        elif key and ln.startswith("  "):
            out[key] += ("\n" if out[key] else "") + ln.strip()
    return out


def _routes() -> list:
    rows = [ROUTE.match(ln) for ln in (SKILL / "SKILL.md").read_text(encoding="utf-8").splitlines()]
    return [(m.group(1), m.group(2), m.group(3)) for m in rows if m]


def test_skill_md_is_the_fleet_entry_point():
    fm = _frontmatter(SKILL / "SKILL.md")
    assert fm["name"] == "fleet" == SKILL.name
    assert len(fm["description"]) <= 1024  # the agentskills.io cap; the skill budget truncates beyond it
    assert len((SKILL / "SKILL.md").read_text(encoding="utf-8").splitlines()) < 120  # an entry point, not the manual


def test_every_route_in_skill_md_names_a_workflow_file_that_exists():
    routes = _routes()
    assert routes, "SKILL.md has no workflow routing table"
    for name, text, target in routes:
        assert text == target == "workflows/%s.md" % name, (name, text, target)
        path = SKILL / target
        assert path.is_file(), "SKILL.md routes %s to %s, which does not exist" % (name, target)
        body = path.read_text(encoding="utf-8")
        assert re.search(r"(^## Trigger$|\*\*Trigger:\*\*)", body, re.M), "%s states no trigger" % target
        assert re.search(r"(^## Check$|\*\*Check:\*\*)", body, re.M), "%s states no check" % target


def test_the_cli_lists_exactly_the_routed_workflows():
    assert [n for n, _ in fleet_reconcile.WORKFLOWS] == [n for n, _, _ in _routes()]
    on_disk = sorted(p.stem for p in (SKILL / "workflows").glob("*.md"))
    assert on_disk == sorted(n for n, _ in fleet_reconcile.WORKFLOWS)  # no workflow file the table doesn't route


def test_fleet_help_lists_the_workflows_and_each_procedure_prints():
    out = subprocess.run(["/bin/sh", str(SCRIPTS / "fleet"), "--help"], capture_output=True, text=True)
    assert out.returncode == 0
    for name, _ in fleet_reconcile.WORKFLOWS:
        assert re.search(r"^  %s\s" % re.escape(name), out.stdout, re.M), name
    for name, _ in fleet_reconcile.WORKFLOWS[1:]:
        shown = subprocess.run(["/bin/sh", str(SCRIPTS / "fleet"), name], capture_output=True, text=True)
        assert shown.returncode == 0 and "## Check" in shown.stdout, name


def test_the_alias_skill_resolves_and_points_at_fleet():
    fm = _frontmatter(ALIAS / "SKILL.md")
    assert fm["name"] == "fleet-reconcile" == ALIAS.name and fm["deprecated"] == "fleet"
    assert "../fleet/SKILL.md" in (ALIAS / "SKILL.md").read_text(encoding="utf-8")
    assert sorted(p.name for p in (ALIAS / "scripts").iterdir()) == ["fleet", "install.sh", "tick.sh"]


@pytest.mark.parametrize("via_link", [False, True])
def test_the_alias_scripts_forward_to_fleet(tmp_path, via_link):
    """The old paths, directly and through a directory symlink like ~/.claude/skills/fleet-reconcile."""
    root = ALIAS
    if via_link:
        root = tmp_path / "fleet-reconcile"
        root.symlink_to(ALIAS)
    new = subprocess.run(["/bin/sh", str(SCRIPTS / "fleet"), "workflows"], capture_output=True, text=True)
    old = subprocess.run(["/bin/sh", str(root / "scripts" / "fleet"), "workflows"], capture_output=True, text=True)
    assert old.returncode == 0 and old.stdout == new.stdout
    assert "deprecated, renamed to fleet" in old.stderr
    inst = subprocess.run(["/bin/bash", str(root / "scripts" / "install.sh"), "--help"], capture_output=True, text=True)
    assert inst.returncode == 0 and "reconcile workflow" in inst.stdout and "deprecated" in inst.stderr
    tick = subprocess.run(["/bin/bash", str(root / "scripts" / "tick.sh")], capture_output=True, text=True,
                          env={k: v for k, v in os.environ.items() if k not in ("FLEET_SCOPE", "FLEET_CHILD")})
    assert tick.returncode == 2 and "tick.sh: FLEET_SCOPE" in tick.stderr  # tick.sh's own refusal: it ran


def test_the_alias_send_gate_fails_closed_when_fleet_is_gone(tmp_path):
    """A PreToolUse hook lets the tool run on any exit but 0 or 2: the alias keeps fleet's 2."""
    copy = tmp_path / "orchestration" / "fleet-reconcile" / "scripts"
    copy.mkdir(parents=True)
    (copy / "fleet").write_text((ALIAS / "scripts" / "fleet").read_text())
    r = subprocess.run(["/bin/sh", str(copy / "fleet"), "send-gate", "pre"], capture_output=True, text=True)
    assert r.returncode == 2


def _flat_install(root: Path, names) -> Path:
    """A per-skill install's layout: each named skill a sibling under one root (~/.agents/skills)."""
    import shutil
    root.mkdir()
    for name in names:
        shutil.copytree(str(SKILL.parent / name), str(root / name),
                        ignore=shutil.ignore_patterns("__pycache__", "tests"))
    return root


def test_the_alias_installed_alone_says_to_install_fleet(tmp_path):
    root = _flat_install(tmp_path / "skills", ["fleet-reconcile"])
    r = subprocess.run(["/bin/sh", str(root / "fleet-reconcile" / "scripts" / "fleet"), "workflows"],
                       capture_output=True, text=True)
    assert r.returncode == 70 and "--skill fleet" in r.stderr and r.stdout == ""
    gate = subprocess.run(["/bin/sh", str(root / "fleet-reconcile" / "scripts" / "fleet"), "send-gate", "pre"],
                          capture_output=True, text=True)
    assert gate.returncode == 2  # a hook that blocks, not one that lets the tool run
    for script in ("install.sh", "tick.sh"):
        r = subprocess.run(["/bin/bash", str(root / "fleet-reconcile" / "scripts" / script)],
                           capture_output=True, text=True)
        assert r.returncode == 70 and "--skill fleet" in r.stderr, script


def test_the_alias_installed_beside_fleet_forwards(tmp_path):
    root = _flat_install(tmp_path / "skills", ["fleet-reconcile", "fleet", "ctx-core"])
    r = subprocess.run(["/bin/sh", str(root / "fleet-reconcile" / "scripts" / "fleet"), "workflows"],
                       capture_output=True, text=True)
    assert r.returncode == 0 and str(root / "fleet" / "workflows" / "launch.md") in r.stdout


# --- close-out's check: the script in workflows/close-out.md, run as written -----------------------

def _close_out_script() -> str:
    body = (SKILL / "workflows" / "close-out.md").read_text(encoding="utf-8")
    check = body.split("## Check", 1)[1]
    return re.search(r"```bash\n(.*?)```", check, re.S).group(1)


@pytest.fixture
def close_out(tmp_path):
    origin, wt = tmp_path / "origin.git", tmp_path / "wt"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(wt)], check=True, capture_output=True)
    git = lambda *a: subprocess.run(["git", "-C", str(wt), *a], check=True, capture_output=True, text=True)
    commit = lambda m: git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", m)
    commit("base")
    git("push", "-q", "origin", "HEAD:main")
    git("fetch", "-q", "origin")
    git("checkout", "-q", "-b", "feat")
    commit("work")  # the session's own work: not in origin/main
    home = tmp_path / "home"
    (home / ".paseo" / "agents" / "w").mkdir(parents=True)
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    gh = bin_ / "gh"
    gh.write_text('#!/bin/sh\n[ -n "$STUB_GH_FAIL" ] && { echo "gh: boom" >&2; exit 1; }\nprintf "%s" "$STUB_PRS"\n')
    gh.chmod(0o755)
    script = _close_out_script().replace("<wt>", str(wt)).replace("<owner/repo>", "o/r") \
        .replace("<branch>", "feat").replace("<id>", "aaaaaaaa")

    def run(prs="[]", **env):
        e = dict(os.environ, HOME=str(home), PATH="%s:%s" % (bin_, os.environ["PATH"]), STUB_PRS=prs, **env)
        return subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, env=e)

    run.head = git("rev-parse", "HEAD").stdout.strip()
    run.wt, run.git, run.home, run.commit = wt, git, home, commit
    return run


def _pr(state, oid):
    import json
    return json.dumps([{"number": 7, "state": state, "headRefOid": oid}])


def test_close_out_finished_only_when_a_merged_pr_carries_head(close_out):
    ok = close_out(_pr("MERGED", close_out.head))
    assert ok.returncode == 0 and ok.stdout.startswith("FINISHED: PR merged"), ok.stderr


def test_close_out_finishes_a_session_with_no_work_of_its_own_without_asking_github(close_out):
    close_out.git("reset", "-q", "--hard", "origin/main")  # HEAD already in the default branch
    ok = close_out("[]", STUB_GH_FAIL="1")
    assert ok.returncode == 0 and "no work of its own" in ok.stdout, ok.stderr


@pytest.mark.parametrize("case", ["never pushed, no PR", "commit after the merge", "PR still open",
                                  "dirty tree", "gh fails", "a live child", "an unreadable registry file"])
def test_close_out_refuses_what_is_not_finished(close_out, case):
    import json
    prs = _pr("MERGED", close_out.head)
    env = {}
    if case == "never pushed, no PR":
        prs = "[]"
    elif case == "commit after the merge":
        close_out.commit("more")
    elif case == "PR still open":
        prs = _pr("OPEN", close_out.head)
    elif case == "dirty tree":
        (close_out.wt / "f").write_text("x")
    elif case == "gh fails":
        env["STUB_GH_FAIL"] = "1"
    elif case == "an unreadable registry file":
        (close_out.home / ".paseo" / "agents" / "w" / "half.json").write_text('{"id": "x')
    elif case == "a live child":
        (close_out.home / ".paseo" / "agents" / "w" / "c.json").write_text(json.dumps(
            {"id": "cccccccc-1", "archivedAt": None, "labels": {"paseo.parent-agent-id": "aaaaaaaa-1"}}))
    r = close_out(prs, **env)
    assert r.returncode == 1 and "NOT FINISHED" in r.stderr and "FINISHED" not in r.stdout, (case, r.stdout, r.stderr)


def test_the_launch_checks_parse_against_the_installed_bstack():
    """launch.md's check lines, run as written with an id that doesn't exist: bstack must get as far as
    looking the id up (exit 1, "not found"), not refuse the argument shape (exit 2, usage)."""
    import shutil
    bstack = shutil.which("bstack") or os.path.expanduser("~/.claude/skills/bstack/bin/bstack")
    if not os.access(bstack, os.X_OK):
        pytest.skip("no bstack on this machine")
    check = (SKILL / "workflows" / "launch.md").read_text(encoding="utf-8").split("## Check", 1)[1]
    lines = [ln.split("#", 1)[0].strip() for ln in re.search(r"```bash\n(.*?)```", check, re.S).group(1).splitlines()]
    assert len([ln for ln in lines if ln]) == 2
    for ln in filter(None, lines):
        argv = [bstack] + re.sub(r"<[a-z-]+>", "no-such-id-bro3122", ln).split()[1:]
        r = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        assert r.returncode == 1 and "not found" in r.stderr and "usage:" not in r.stderr, (ln, r.stderr)
