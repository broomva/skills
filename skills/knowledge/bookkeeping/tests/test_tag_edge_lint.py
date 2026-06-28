"""Tests for the controlled-vocab tag lint + contradicts-resolution lint (BRO-1452).

- _lint_tags: warns on missing tags, type-redundant tags (already encoded by
  `type:`), and off-vocabulary tags (when research/entities/_tags.md exists).
- _lint_contradicts_resolution: warns when a NON-EMPTY contradicts list lacks a
  body resolution section (the entity-schema rule), making the edge trustworthy.

All warnings (non-breaking).
"""
import pytest

import bookkeeping
from bookkeeping import _lint_contradicts_resolution, _lint_tags


@pytest.fixture
def vocab(tmp_path, monkeypatch):
    """Point ENTITIES_DIR at a tmp dir with a small _tags.md, reset the cache."""
    (tmp_path / "_tags.md").write_text(
        "# Controlled Tag Vocabulary\n## Domain\n"
        "- `control-theory` — gloss\n- `governance` — gloss\n- `knowledge-graph` — gloss\n"
    )
    monkeypatch.setattr(bookkeeping, "ENTITIES_DIR", tmp_path)
    monkeypatch.setattr(bookkeeping, "_TAG_VOCAB_CACHE", False)
    yield
    monkeypatch.setattr(bookkeeping, "_TAG_VOCAB_CACHE", False)


def _msgs(errs):
    return [e.message for e in errs]


def test_load_vocab(vocab):
    v = bookkeeping.load_tag_vocab()
    assert v == {"control-theory", "governance", "knowledge-graph"}


def test_offvocab_tag_warns(vocab):
    errs = _lint_tags("p.md", {"type": "concept", "tags": ["governance", "made-up-tag"]}, "concept")
    assert any("not in controlled vocabulary" in m and "made-up-tag" in m for m in _msgs(errs))
    assert all(e.severity == "warning" for e in errs)


def test_type_redundant_tag_warns(vocab):
    # tag == the entity's OWN type → "redundant with type:"
    errs = _lint_tags("p.md", {"type": "concept", "tags": ["concept", "governance"]}, "concept")
    assert any("redundant with type" in m and "'concept'" in m for m in _msgs(errs))


def test_other_type_name_tag_warns_distinctly(vocab):
    # tag is a DIFFERENT entity-type name (P20 nit): not "redundant with type"
    # (the type is concept, not tool) but still invalid as a tag.
    errs = _lint_tags("p.md", {"type": "concept", "tags": ["tool", "governance"]}, "concept")
    msgs = _msgs(errs)
    assert any("entity-type name, not a valid tag" in m and "'tool'" in m for m in msgs)
    assert not any("redundant with type" in m for m in msgs)


def test_all_canonical_clean(vocab):
    errs = _lint_tags("p.md", {"type": "concept", "tags": ["governance", "control-theory"]}, "concept")
    assert errs == []


def test_missing_tags_warns(vocab):
    errs = _lint_tags("p.md", {"type": "concept", "tags": []}, "concept")
    assert any("no tags" in m for m in _msgs(errs))


def test_offvocab_noop_without_tags_file(tmp_path, monkeypatch):
    # No _tags.md → off-vocab check is skipped, but type-redundant still fires.
    monkeypatch.setattr(bookkeeping, "ENTITIES_DIR", tmp_path)
    monkeypatch.setattr(bookkeeping, "_TAG_VOCAB_CACHE", False)
    errs = _lint_tags("p.md", {"type": "tool", "tags": ["anything-goes", "tool"]}, "tool")
    msgs = _msgs(errs)
    assert not any("not in controlled vocabulary" in m for m in msgs)  # off-vocab skipped
    assert any("redundant with type" in m for m in msgs)               # type-redundant still fires


# ── contradicts-resolution ──

def test_contradicts_without_resolution_warns():
    errs = _lint_contradicts_resolution("p.md", {"contradicts": ["[[other]]"]}, "# Title\n\nNo resolution here.")
    assert len(errs) == 1 and "no resolution section" in errs[0].message
    assert errs[0].severity == "warning"


def test_contradicts_with_resolution_clean():
    body = "# Title\n\n### Contradictions\n\nResolved: A supersedes B because…\n"
    errs = _lint_contradicts_resolution("p.md", {"contradicts": ["[[other]]"]}, body)
    assert errs == []


def test_empty_contradicts_clean():
    assert _lint_contradicts_resolution("p.md", {"contradicts": []}, "body") == []


def test_no_contradicts_clean():
    assert _lint_contradicts_resolution("p.md", {}, "body") == []
