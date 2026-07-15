"""Unit tests for `_resolve_knowledge_paths` — repo-native, config-driven path
resolution (BRO-1903).

Locks two things:
  1. The backward-compat invariant — with no top-level `knowledge:` block and no
     KG_* env, the resolver returns exactly today's ~/broomva layout. A nested
     `plants.knowledge` control-plant block must NOT be mistaken for the config.
  2. The precedence — config (a top-level `knowledge:` block in the nearest
     .control/policy.yaml) > KG_*/BROOMVA_ROOT env > default.

`_resolve_knowledge_paths(start_dir=..., env=...)` is pure, so every case is
driven with an explicit isolated `start_dir` (pytest tmp_path, which lives
outside any repo with a .control/policy.yaml) and an explicit `env` dict.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import bookkeeping  # noqa: E402 (path injected by conftest.py)


def _write_policy(repo: Path, knowledge_block: str | None) -> Path:
    """Write repo/.control/policy.yaml with a benign gates: block plus an
    optional trailing top-level YAML fragment (e.g. a knowledge: block)."""
    ctl = repo / ".control"
    ctl.mkdir(parents=True, exist_ok=True)
    body = "gates:\n  - G1\n"
    if knowledge_block is not None:
        body += knowledge_block
    policy = ctl / "policy.yaml"
    policy.write_text(body)
    return policy


DEFAULT_ROOT = Path.home() / "broomva"


class TestDefaultAndEnv:
    def test_default_no_config_no_env(self, tmp_path):
        root, ent, cat = bookkeeping._resolve_knowledge_paths(start_dir=tmp_path, env={})
        assert root == DEFAULT_ROOT
        assert ent == DEFAULT_ROOT / "research" / "entities"
        assert cat == DEFAULT_ROOT / "docs" / "knowledge-index.md"

    def test_broomva_root_env_honored(self, tmp_path):
        root, ent, cat = bookkeeping._resolve_knowledge_paths(
            start_dir=tmp_path, env={"BROOMVA_ROOT": "/opt/graph"})
        assert root == Path("/opt/graph")
        assert ent == Path("/opt/graph/research/entities")
        assert cat == Path("/opt/graph/docs/knowledge-index.md")

    def test_kg_env_overrides_each_key(self, tmp_path):
        root, ent, cat = bookkeeping._resolve_knowledge_paths(
            start_dir=tmp_path,
            env={"KG_ROOT": "/r", "KG_ENTITIES_DIR": "/e/ents",
                 "KG_CATALOG": "/c/cat.md"})
        assert root == Path("/r")
        assert ent == Path("/e/ents")       # independent of root
        assert cat == Path("/c/cat.md")

    def test_kg_root_only_derives_rest(self, tmp_path):
        root, ent, cat = bookkeeping._resolve_knowledge_paths(
            start_dir=tmp_path, env={"KG_ROOT": "/r"})
        assert root == Path("/r")
        assert ent == Path("/r/research/entities")
        assert cat == Path("/r/docs/knowledge-index.md")

    def test_empty_broomva_root_falls_back_to_default(self, tmp_path):
        root, _, _ = bookkeeping._resolve_knowledge_paths(
            start_dir=tmp_path, env={"BROOMVA_ROOT": ""})
        assert root == DEFAULT_ROOT


class TestConfigBlock:
    def test_block_relocates_to_docs_research(self, tmp_path):
        # The SRI opt-in shape: entities + catalog under docs/research.
        repo = tmp_path / "repo"
        _write_policy(repo,
                      "knowledge:\n"
                      "  entities_dir: docs/research/entities\n"
                      "  catalog_path: docs/research/knowledge-index.md\n")
        deep = repo / "src" / "deep"           # discovered by walking up
        deep.mkdir(parents=True)
        root, ent, cat = bookkeeping._resolve_knowledge_paths(start_dir=deep, env={})
        assert root == repo                     # block present, no explicit root → repo
        assert ent == repo / "docs" / "research" / "entities"
        assert cat == repo / "docs" / "research" / "knowledge-index.md"

    def test_explicit_root_key(self, tmp_path):
        repo = tmp_path / "repo"
        _write_policy(repo, "knowledge:\n  root: /custom/graph\n")
        root, ent, cat = bookkeeping._resolve_knowledge_paths(start_dir=repo, env={})
        assert root == Path("/custom/graph")
        assert ent == Path("/custom/graph/research/entities")
        assert cat == Path("/custom/graph/docs/knowledge-index.md")

    def test_absolute_paths_in_block_respected(self, tmp_path):
        repo = tmp_path / "repo"
        _write_policy(repo, "knowledge:\n  catalog_path: /abs/cat.md\n")
        _, _, cat = bookkeeping._resolve_knowledge_paths(start_dir=repo, env={})
        assert cat == Path("/abs/cat.md")

    def test_config_beats_env(self, tmp_path):
        repo = tmp_path / "repo"
        _write_policy(repo, "knowledge:\n  entities_dir: docs/research/entities\n")
        root, ent, _ = bookkeeping._resolve_knowledge_paths(
            start_dir=repo, env={"BROOMVA_ROOT": "/ignored"})
        assert root == repo                     # block presence beats BROOMVA_ROOT
        assert ent == repo / "docs" / "research" / "entities"


class TestBackwardCompatGuards:
    def test_nested_plants_knowledge_ignored(self, tmp_path):
        # The real personal-policy shape: knowledge lives under plants:, which
        # must NOT be read as the top-level config. This is the linchpin that
        # keeps the ~/broomva graph on the default paths.
        repo = tmp_path / "repo"
        _write_policy(repo,
                      "plants:\n"
                      "  knowledge:\n"
                      "    type: cyber\n"
                      "    entities_dir: SHOULD_NOT_BE_READ\n")
        root, ent, _ = bookkeeping._resolve_knowledge_paths(start_dir=repo, env={})
        assert root == DEFAULT_ROOT
        assert "SHOULD_NOT_BE_READ" not in str(ent)
        assert ent == DEFAULT_ROOT / "research" / "entities"

    def test_empty_knowledge_block_is_default(self, tmp_path):
        repo = tmp_path / "repo"
        _write_policy(repo, "knowledge:\n")     # null value → absent
        root, _, _ = bookkeeping._resolve_knowledge_paths(start_dir=repo, env={})
        assert root == DEFAULT_ROOT

    def test_missing_policy_is_default(self, tmp_path):
        # No .control/policy.yaml anywhere up-tree from an isolated dir.
        root, _, _ = bookkeeping._resolve_knowledge_paths(start_dir=tmp_path, env={})
        assert root == DEFAULT_ROOT

    def test_non_str_value_degrades_not_crashes(self, tmp_path, capsys):
        # YAML coerces `entities_dir: 123` → int; a bare date/bool/list likewise.
        # This must NOT reach Path(...) and crash the module at import — it must
        # warn and degrade to the default (the _read_knowledge_block contract).
        repo = tmp_path / "repo"
        _write_policy(repo, "knowledge:\n  entities_dir: 123\n")
        root, ent, _ = bookkeeping._resolve_knowledge_paths(start_dir=repo, env={})
        assert root == DEFAULT_ROOT            # bad value ignored → default stands
        assert ent == DEFAULT_ROOT / "research" / "entities"
        assert "must be a string path" in capsys.readouterr().err

    def test_typo_key_does_not_hijack_root(self, tmp_path, capsys):
        # A block with only an unrecognized (typo'd) key must warn and NOT
        # silently anchor root to the repo, dropping the env root.
        repo = tmp_path / "repo"
        _write_policy(repo, "knowledge:\n  entities_dirr: docs/research/entities\n")
        root, ent, _ = bookkeeping._resolve_knowledge_paths(
            start_dir=repo, env={"BROOMVA_ROOT": "/env/root"})
        assert root == Path("/env/root")       # env honored, repo NOT hijacked
        assert ent == Path("/env/root/research/entities")
        assert "unrecognized knowledge.entities_dirr" in capsys.readouterr().err

    def test_real_personal_policy_resolves_to_default(self):
        """Guard the actual host graph: ~/broomva/.control/policy.yaml has a
        nested plants.knowledge block but no top-level knowledge: → the resolver
        must return the default paths. Skips where there is no personal graph
        (CI runners, co-developers)."""
        personal = Path.home() / "broomva"
        policy = personal / ".control" / "policy.yaml"
        if not policy.is_file():
            pytest.skip("no personal ~/broomva/.control/policy.yaml on this host")
        root, ent, cat = bookkeeping._resolve_knowledge_paths(start_dir=personal, env={})
        assert root == personal
        assert ent == personal / "research" / "entities"
        assert cat == personal / "docs" / "knowledge-index.md"
