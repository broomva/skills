"""System 2's cache: written atomically, read consistently, collected safely,
and the same items always give the same bytes."""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

import s1_support as S
import ctx_keys as K
import ctx_s1
import ctx_s2


def _items(tag: str, n: int = 5):
    out = []
    for i in range(n):
        out.append(ctx_s2.make_item("entity:x/%s-%d" % (tag, i), "entity", "claim %s %d" % (tag, i),
                                    "research/entities/x/%s-%d.md" % (tag, i), 0.0,
                                    {"p": ["p:scripts/a%d.py" % i], "w": ["w:%s" % tag, "w:alpha"]},
                                    ["o:research/entities/x/%s-%d.md" % (tag, i)]))
    return out


def _write(store: Path, tag: str, now: float):
    items = _items(tag)
    r = ctx_s2.BM25Ranker()
    r.fit(items)
    return ctx_s2.write_cache(store, items, r, now=now)


def test_the_current_link_moves_only_to_a_complete_build(tmp_path):
    store = tmp_path / "store"
    first = _write(store, "one", 1_000_000.0)
    assert os.readlink(str(store / "rank-current")) == first.name
    second = _write(store, "two", 1_000_100.0)
    assert os.readlink(str(store / "rank-current")) == second.name
    assert first.exists()  # the previous build is kept for readers still on it
    third = _write(store, "three", 1_000_200.0)
    assert not first.exists() and second.exists() and third.exists()
    for b in (second, third):
        assert (b / "meta.json").exists() and any((b / "postings").iterdir()) and any((b / "items").iterdir())


def test_a_reader_stays_on_its_build_across_a_swap(tmp_path):
    store = tmp_path / "store"
    _write(store, "one", 1_000_000.0)
    reader = ctx_s1.CacheReader(store)
    before = reader.postings("p:scripts/a0.py")
    assert before
    _write(store, "two", 1_000_100.0)
    assert reader.postings("p:scripts/a0.py") == before  # still its own build
    assert reader.item(before[0][0])["claim"] == "claim one 0"
    fresh = ctx_s1.CacheReader(store)
    assert fresh.item(fresh.postings("p:scripts/a0.py")[0][0])["claim"] == "claim two 0"


def test_a_build_that_dies_midway_leaves_the_current_cache_alone(tmp_path, monkeypatch):
    store = tmp_path / "store"
    good = _write(store, "one", 1_000_000.0)
    calls = {"n": 0}
    real = ctx_s2._write

    def dying(path, data):
        calls["n"] += 1
        if calls["n"] > 3:
            raise OSError("disk full")
        return real(path, data)

    monkeypatch.setattr(ctx_s2, "_write", dying)
    with pytest.raises(OSError):
        _write(store, "two", 1_000_100.0)
    assert os.readlink(str(store / "rank-current")) == good.name
    assert sorted(p.name for p in store.iterdir()) == sorted([good.name, "rank-current"])


def test_collection_never_follows_a_symlink(tmp_path):
    store = tmp_path / "store"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "precious.txt").write_text("keep me")
    store.mkdir()
    os.symlink(str(outside), str(store / "rank-20000101T000000Z-0000000000"))
    for i in range(3):
        _write(store, "b%d" % i, 1_000_000.0 + i * 100)
    assert (outside / "precious.txt").read_text() == "keep me"


def test_the_same_items_give_the_same_bytes(tmp_path):
    a = _write(tmp_path / "a", "one", 1_000_000.0)
    b = _write(tmp_path / "b", "one", 1_000_000.0)
    assert a.name == b.name
    files = lambda d: {str(p.relative_to(d)): p.read_bytes() for p in d.rglob("*") if p.is_file()}
    assert files(a) == files(b)


def test_cache_files_are_private(tmp_path):
    d = _write(tmp_path / "store", "one", 1_000_000.0)
    for p in [d / "meta.json"] + list((d / "postings").iterdir()):
        assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_a_live_build_refuses_an_eval_ranker(world):
    S.write_corpus(world)
    import subprocess, sys
    r = subprocess.run([sys.executable, "-I", str(S.S1CLI), "build", "--no-network", "--ranker", "ppr"],
                       cwd=str(world.broomva), capture_output=True, text=True)
    assert r.returncode == 2 and "only bm25" in r.stderr


def test_the_ranker_seam_scores_a_linked_item(tmp_path):
    """The traversal prototype fills the same postings: an item that does not
    hold a key still ranks for it when a holder links to it."""
    items = _items("one", 3)
    items[0]["links"] = [2]
    items[2]["keys"] = {"w": ["w:zzz"]}  # item 2 no longer holds p:scripts/a0.py
    import ctx_s2_ppr

    ppr = ctx_s2_ppr.PPRRanker()
    ppr.fit(items)
    bm = ctx_s2.BM25Ranker()
    bm.fit(items)
    assert 2 not in [i for i, _ in bm.postings()["p:scripts/a0.py"]]
    assert 2 in [i for i, _ in ppr.postings()["p:scripts/a0.py"]]


def test_bm25_keeps_a_rare_key_and_drops_a_hub(tmp_path):
    items = []
    for i in range(20):
        keys = {"w": ["w:common", "w:x%d" % i]}
        items.append(ctx_s2.make_item("e:%d" % i, "entity", "c", "s", 0.0, keys, []))
    r = ctx_s2.BM25Ranker(max_df_share=0.2)
    r.fit(items)
    post = r.postings()
    assert "w:common" not in post  # held by every item: names nothing
    assert post["w:x3"][0][0] == 3
