"""BRO-2957: a repo's auto_merge block that p9 cannot parse must not kill
`watch`, which never acts on auto_merge. The merge paths stay fail-closed."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent / "scripts"
_FIXTURES = _HERE / "fixtures"
_FOREIGN = _FIXTURES / "policy-foreign-auto-merge.yaml"
sys.path.insert(0, str(_SCRIPTS))

SRI_KEYS = ["base_branch_patterns", "head_branch_patterns", "migration_paths",
            "never_auto_merge_labels", "p20"]


class _FakeProc:
    pid = 12345

    def wait(self):
        return 0


def _p9(tmp_path, monkeypatch, policy: Path):
    monkeypatch.setenv("BROOMVA_P9_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("BROOMVA_P9_POLICY", str(policy))
    monkeypatch.setenv("BROOMVA_P9_REPO", "broomva/test")
    if "p9" in sys.modules:
        del sys.modules["p9"]
    return importlib.import_module("p9")


def _malformed(tmp_path: Path) -> Path:
    # A block that is wrong by p9's own schema, not merely foreign: a quoted
    # "true" must never be read as enabled.
    p = tmp_path / "malformed.yaml"
    p.write_text((_FIXTURES / "policy-good.yaml").read_text(encoding="utf-8")
                 + "\nauto_merge:\n  enabled: \"true\"\n", encoding="utf-8")
    return p


@pytest.mark.parametrize("policy", ["foreign", "malformed"])
def test_watch_loads_and_folds(tmp_path, monkeypatch, capsys, policy):
    path = _FOREIGN if policy == "foreign" else _malformed(tmp_path)
    p9 = _p9(tmp_path, monkeypatch, path)
    monkeypatch.setattr(p9, "spawn_watcher", lambda *a, **kw: _FakeProc())
    rc = p9.main(["watch", "100", "--repo", "broomva/test"])
    assert rc == 0, capsys.readouterr().err
    assert p9.current_pr_state(100, repo="broomva/test") == p9.PRState.GREEN
    assert "ignoring auto_merge on a read-only path" in capsys.readouterr().err


def test_read_only_load_disables_the_unparseable_block(tmp_path, monkeypatch):
    p9 = _p9(tmp_path, monkeypatch, _FOREIGN)
    cfg = p9.load_policy(validate_auto_merge=False)
    assert cfg.auto_merge.enabled is False
    assert cfg.ci_watch.enabled is True


def test_strict_load_still_rejects_the_sri_keys(tmp_path, monkeypatch):
    p9 = _p9(tmp_path, monkeypatch, _FOREIGN)
    with pytest.raises(p9.PolicyError) as e:
        p9.load_policy()
    for k in SRI_KEYS:
        assert k in str(e.value)


@pytest.mark.parametrize("policy,why", [
    ("foreign", "auto_merge has unknown key(s)"),
    ("malformed", "auto_merge.enabled must be true or false"),
])
def test_auto_merge_refuses(tmp_path, monkeypatch, capsys, policy, why):
    path = _FOREIGN if policy == "foreign" else _malformed(tmp_path)
    p9 = _p9(tmp_path, monkeypatch, path)
    merged = []
    monkeypatch.setattr(p9.subprocess, "run",
                        lambda *a, **kw: merged.append(a) or pytest.fail("reached gh"))
    rc = p9.main(["auto-merge", "100", "--repo", "broomva/test"])
    assert rc == p9.EXIT_POLICY_ERROR
    assert merged == []
    # Refused BECAUSE the block is rejected, not because a lax load read it
    # as disabled: that would also exit 2, and would hide a merge path that
    # stopped validating.
    err = capsys.readouterr().err
    assert why in err
    assert "read-only path" not in err
