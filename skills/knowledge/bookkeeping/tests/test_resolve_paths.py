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

    def test_kg_no_policy_bypasses_config(self, tmp_path):
        # KG_NO_POLICY=1 skips the policy layer entirely so KG_*/BROOMVA_ROOT
        # pin the graph unambiguously (used by the bench harness's child loader).
        repo = tmp_path / "repo"
        _write_policy(repo, "knowledge:\n  entities_dir: docs/research/entities\n")
        root, ent, _ = bookkeeping._resolve_knowledge_paths(
            start_dir=repo, env={"KG_NO_POLICY": "1", "BROOMVA_ROOT": "/env/root"})
        assert root == Path("/env/root")        # block ignored, env wins
        assert ent == Path("/env/root/research/entities")


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
        # A host that legitimately opts into a top-level knowledge: block would
        # NOT resolve to the default — skip rather than assert against mutable
        # host config (the synthetic nested-plants test already locks the
        # backward-compat mechanism).
        try:
            import yaml
            data = yaml.safe_load(policy.read_text()) or {}
            if isinstance(data, dict) and isinstance(data.get("knowledge"), dict):
                pytest.skip("host policy opts into a top-level knowledge: block")
        except ImportError:
            pass  # no yaml → resolver ignores any block → default holds anyway
        root, ent, cat = bookkeeping._resolve_knowledge_paths(start_dir=personal, env={})
        assert root == personal
        assert ent == personal / "research" / "entities"
        assert cat == personal / "docs" / "knowledge-index.md"


class TestDisplayPathNeverCrashes:
    """`_display_path` must format a configured path OUTSIDE the root (an
    absolute knowledge.catalog_path / entities_dir) as absolute instead of
    raising ValueError on `.relative_to` — the crash CodeRabbit flagged."""

    def test_relative_when_inside_root(self, monkeypatch, tmp_path):
        monkeypatch.setattr(bookkeeping, "BROOMVA_ROOT", tmp_path)
        assert bookkeeping._display_path(tmp_path / "docs" / "x.md") == Path("docs/x.md")

    def test_absolute_when_outside_root(self, monkeypatch, tmp_path):
        monkeypatch.setattr(bookkeeping, "BROOMVA_ROOT", tmp_path)
        outside = Path("/some/abs/cat.md")
        assert bookkeeping._display_path(outside) == outside     # no ValueError

    def test_cmd_index_catalog_outside_root_no_crash(self, tmp_path, monkeypatch):
        # End-to-end: an absolute CATALOG_PATH outside BROOMVA_ROOT must write +
        # print the completion line without crashing (out_path.relative_to).
        root = tmp_path / "graph"
        entities = root / "research" / "entities" / "concept"
        entities.mkdir(parents=True)
        (entities / "x.md").write_text(
            "---\ntype: concept\nstatus: entity\ncore_claim: A claim.\n---\nBody.\n")
        catalog = tmp_path / "outside" / "cat.md"    # sibling of root → outside it
        catalog.parent.mkdir()
        monkeypatch.setattr(bookkeeping, "BROOMVA_ROOT", root)
        monkeypatch.setattr(bookkeeping, "ENTITIES_DIR", root / "research" / "entities")
        monkeypatch.setattr(bookkeeping, "CATALOG_PATH", catalog)
        import argparse
        bookkeeping.cmd_index(argparse.Namespace(dry_run=False))  # must NOT raise
        assert catalog.is_file()


# ── Enclosing checkout, worktree-aware (BRO-2614) ─────────────────────────────

def _checkout(path: Path, *, worktree_of: Path | None = None, graph: bool = True) -> Path:
    """A git toplevel: a `.git` dir with HEAD, or a worktree's `.git` FILE whose
    gitdir target has HEAD — the shapes git itself writes."""
    path.mkdir(parents=True, exist_ok=True)
    if worktree_of is None:
        (path / ".git").mkdir()
        (path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    else:
        gitdir = worktree_of / ".git" / "worktrees" / path.name
        gitdir.mkdir(parents=True, exist_ok=True)
        (gitdir / "HEAD").write_text("ref: refs/heads/feature\n")
        (path / ".git").write_text(f"gitdir: {gitdir}\n")
    if graph:
        (path / "research" / "entities").mkdir(parents=True)
    return path


class TestEnclosingCheckout:
    def test_worktree_resolves_to_itself_not_the_main_checkout(self, tmp_path):
        main = _checkout(tmp_path / "main")
        wt = _checkout(tmp_path / "wt", worktree_of=main)
        root, ent, cat = bookkeeping._resolve_knowledge_paths(
            start_dir=wt / "research" / "entities", env={})
        assert root == wt
        assert ent == wt / "research" / "entities"
        assert cat == wt / "docs" / "knowledge-index.md"

    def test_worktree_nested_inside_the_main_checkout(self, tmp_path):
        main = _checkout(tmp_path / "main")
        wt = _checkout(main / ".worktrees" / "x", worktree_of=main)
        root, _, _ = bookkeeping._resolve_knowledge_paths(start_dir=wt, env={})
        assert root == wt

    def test_main_checkout_resolves_to_itself(self, tmp_path):
        main = _checkout(tmp_path / "main")
        root, _, _ = bookkeeping._resolve_knowledge_paths(start_dir=main / "docs", env={})
        assert root == main

    def test_nested_repo_without_a_graph_is_walked_past(self, tmp_path):
        main = _checkout(tmp_path / "main")
        skills = _checkout(main / "skills", graph=False)
        root, _, _ = bookkeeping._resolve_knowledge_paths(start_dir=skills / "x", env={})
        assert root == main

    def test_graph_dir_without_git_is_not_a_checkout(self, tmp_path):
        (tmp_path / "loose" / "research" / "entities").mkdir(parents=True)
        root, _, _ = bookkeeping._resolve_knowledge_paths(start_dir=tmp_path / "loose", env={})
        assert root == DEFAULT_ROOT

    @pytest.mark.parametrize("dotgit", [
        "file:not git",                       # a text file named .git
        "file:gitdir: /nonexistent/wt",       # gitdir target missing
        "dir-without-HEAD",                   # an empty .git directory
    ])
    def test_a_dotgit_that_is_not_a_checkout_is_not_adopted(self, tmp_path, dotgit):
        d = tmp_path / "fake"
        (d / "research" / "entities").mkdir(parents=True)
        if dotgit.startswith("file:"):
            (d / ".git").write_text(dotgit[len("file:"):] + "\n")
        else:
            (d / ".git").mkdir()
        root, _, _ = bookkeeping._resolve_knowledge_paths(start_dir=d, env={})
        assert root == DEFAULT_ROOT

    def test_relative_gitdir_resolves_against_the_checkout(self, tmp_path):
        main = _checkout(tmp_path / "main")
        wt = tmp_path / "wt"
        (wt / "research" / "entities").mkdir(parents=True)
        (main / ".git" / "worktrees" / "wt").mkdir(parents=True)
        (main / ".git" / "worktrees" / "wt" / "HEAD").write_text("x\n")
        (wt / ".git").write_text("gitdir: ../main/.git/worktrees/wt\n")
        root, _, _ = bookkeeping._resolve_knowledge_paths(start_dir=wt, env={})
        assert root == wt

    @pytest.mark.parametrize("key", ["BROOMVA_ROOT", "KG_ROOT"])
    def test_explicit_override_beats_the_cwd_checkout(self, tmp_path, key):
        wt = _checkout(tmp_path / "wt", worktree_of=tmp_path / "main")
        root, _, _ = bookkeeping._resolve_knowledge_paths(start_dir=wt, env={key: "/env/root"})
        assert root == Path("/env/root")


def test_index_from_a_worktree_never_writes_the_main_checkout(tmp_path):
    """End to end, as the #789 drain ran it: `bookkeeping index` from a worktree,
    no KG_* env. HOME is faked so the legacy default ~/broomva IS the main
    checkout — the pre-fix resolver writes there."""
    import os
    import subprocess
    import sys

    home = tmp_path / "home"
    main = _checkout(home / "broomva")
    wt = _checkout(tmp_path / "wt", worktree_of=main)
    for repo, slug in ((main, "main-only"), (wt, "wt-only")):
        d = repo / "research" / "entities" / "concept"
        d.mkdir(parents=True)
        (d / f"{slug}.md").write_text(
            f"---\ntype: concept\nstatus: entity\ncore_claim: The {slug} claim.\n---\nBody.\n")
    main_catalog = main / "docs" / "knowledge-index.md"
    main_catalog.parent.mkdir()
    main_catalog.write_text("SENTINEL — the main checkout's own catalog\n")
    before = main_catalog.read_bytes()

    env = {k: v for k, v in os.environ.items()
           if k not in ("BROOMVA_ROOT", "KG_ROOT", "KG_ENTITIES_DIR", "KG_CATALOG")}
    env.update(HOME=str(home), KG_NO_POLICY="1")
    script = Path(bookkeeping.__file__).resolve()
    res = subprocess.run([sys.executable, str(script), "index"], cwd=wt, env=env,
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr

    assert main_catalog.read_bytes() == before
    wt_catalog = (wt / "docs" / "knowledge-index.md").read_text()
    assert "wt-only" in wt_catalog and "main-only" not in wt_catalog
