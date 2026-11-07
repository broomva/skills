"""Tests for scripts/build_plugin_marketplace.py.

Each case runs the real generator against a tiny fixture repo on disk (two
buckets, three skills) so every expected value can be checked by eye.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_plugin_marketplace.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_plugin_marketplace", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["build_plugin_marketplace"] = mod
    spec.loader.exec_module(mod)
    return mod


bpm = _load_module()


def _skill(root: Path, category: str, name: str) -> None:
    d = root / "skills" / category / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _skill(tmp_path, "research", "checkit")
    _skill(tmp_path, "research", "deep-dive")
    _skill(tmp_path, "models", "bitnet")
    # A nested sub-skill is not a bucket skill and must not be listed.
    nested = tmp_path / "skills/research/checkit/skills/inner"
    nested.mkdir(parents=True)
    (nested / "SKILL.md").write_text("---\nname: inner\ndescription: x\n---\n")
    (tmp_path / "README.md").write_text("### Research — `skills/research/`\n")
    return tmp_path


def _read(repo: Path, rel: str) -> dict:
    return json.loads((repo / ".claude-plugin" / rel).read_text())


def test_one_plugin_per_bucket_plus_bundle(repo: Path) -> None:
    assert bpm.main(["--root", str(repo)]) == 0
    m = _read(repo, "marketplace.json")
    by_name = {p["name"]: p for p in m["plugins"]}
    assert list(by_name) == ["broomva-skills", "models", "research"]
    assert by_name["research"]["source"] == "./skills/research"
    assert by_name["research"]["strict"] is False
    assert by_name["research"]["skills"] == ["./"]
    assert by_name["research"]["description"].startswith("Research skills")
    # No README heading → the directory name is the title.
    assert by_name["models"]["description"].startswith("models skills")
    assert by_name["broomva-skills"]["source"] == "./"
    assert "3 skills across 2 category buckets" in by_name["broomva-skills"]["description"]


def test_bundle_plugin_lists_every_bucket_without_version(repo: Path) -> None:
    bpm.main(["--root", str(repo)])
    p = _read(repo, "plugin.json")
    assert p["name"] == "broomva-skills"
    assert p["skills"] == ["./skills/models", "./skills/research"]
    assert "version" not in p
    assert all("version" not in e for e in _read(repo, "marketplace.json")["plugins"])


def test_check_is_clean_after_write_and_red_on_new_skill(repo: Path, capsys) -> None:
    assert bpm.main(["--root", str(repo), "--check"]) == 1  # nothing written yet
    bpm.main(["--root", str(repo)])
    assert bpm.main(["--root", str(repo), "--check"]) == 0
    _skill(repo, "design", "liquid-dawn")
    capsys.readouterr()
    assert bpm.main(["--root", str(repo), "--check"]) == 1
    err = capsys.readouterr().err
    assert "marketplace.json" in err and "plugin.json" in err


def test_write_is_idempotent(repo: Path) -> None:
    bpm.main(["--root", str(repo)])
    first = {p: p.read_text() for p in (repo / ".claude-plugin").iterdir()}
    bpm.main(["--root", str(repo)])
    assert first == {p: p.read_text() for p in (repo / ".claude-plugin").iterdir()}
