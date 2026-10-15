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
