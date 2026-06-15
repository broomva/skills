#!/usr/bin/env python3
"""
test_ccr.py — unit tests for the ccr reversible-compression primitive (BRO-1521).

Run:
    python3 -m pytest skills/ccr/tests/ -q
    # or, without pytest installed:
    python3 skills/ccr/tests/test_ccr.py

The load-bearing invariant under test: the compact VIEW is lossy, but the
original is ALWAYS recoverable byte-for-byte via the handle (reversible-by-cache).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

# Load the deterministic core from the sibling scripts/ dir (monorepo layout).
SCRIPT = Path(__file__).parent.parent / "scripts" / "ccr.py"
_spec = importlib.util.spec_from_file_location("ccr", SCRIPT)
ccr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ccr)


# --- fixtures ---------------------------------------------------------------
JSON_PAYLOAD = json.dumps(
    [{"id": i, "name": f"row-{i}", "meta": {"score": i * 1.5, "ok": True}} for i in range(200)]
)

CODE_PAYLOAD = '''\
import os
from pathlib import Path

class Widget:
    """A widget."""
    def __init__(self, name):
        self.name = name
        # lots of body lines that should be elided from the outline
        for _ in range(100):
            pass

    def render(self):
        return f"<{self.name}>"

def make(name):
    return Widget(name)
'''

TEXT_PAYLOAD = "\n".join(f"log line {i}: doing work" for i in range(500))


# --- helpers ----------------------------------------------------------------
def _round_trip(payload, content_type, cache_dir):
    res = ccr.compress(payload, content_type, cache_dir=cache_dir)
    got = ccr.retrieve(res["handle"], cache_dir=cache_dir)
    return res, got


# --- tests ------------------------------------------------------------------
def test_roundtrip_is_lossless_for_every_type(tmp_path):
    for payload, ctype in [
        (JSON_PAYLOAD, "json"),
        (CODE_PAYLOAD, "code"),
        (TEXT_PAYLOAD, "text"),
    ]:
        res, got = _round_trip(payload, ctype, tmp_path)
        assert got == payload, f"{ctype}: retrieve must return the EXACT original"
        # the view is genuinely smaller (the whole point)
        assert res["compact_chars"] < res["original_chars"], f"{ctype}: view not smaller"
        assert res["saved_pct"] > 0


def test_auto_detection(tmp_path):
    assert ccr.compress(JSON_PAYLOAD, "auto", cache_dir=tmp_path)["content_type"] == "json"
    assert ccr.compress(CODE_PAYLOAD, "auto", cache_dir=tmp_path)["content_type"] == "code"
    assert ccr.compress(TEXT_PAYLOAD, "auto", cache_dir=tmp_path)["content_type"] == "text"


def test_filename_hint_overrides_content_heuristic(tmp_path):
    # comment-heavy source under-triggers keyword density -> would be "text"...
    # (6 comment lines + 2 keyword-free statements = 0/8 density, well under 0.20)
    comment_heavy = (
        "# header comment\n"
        "# explanation line one\n"
        "# explanation line two\n"
        "# explanation line three\n"
        "# explanation line four\n"
        "# explanation line five\n"
        "value = helper()\n"
        "result = transform(value)\n"
    )
    assert ccr.detect_type(comment_heavy) == "text"  # content alone misses it
    # ...but the .py extension is the stronger signal and wins.
    assert ccr.detect_type(comment_heavy, filename="x.py") == "code"
    res = ccr.compress(comment_heavy, "auto", cache_dir=tmp_path, filename="x.py")
    assert res["content_type"] == "code"
    assert ccr.retrieve(res["handle"], cache_dir=tmp_path) == comment_heavy


def test_handle_is_content_addressed_and_idempotent(tmp_path):
    a = ccr.compress(TEXT_PAYLOAD, "text", cache_dir=tmp_path)
    b = ccr.compress(TEXT_PAYLOAD, "text", cache_dir=tmp_path)
    assert a["handle"] == b["handle"], "identical payloads must share one handle"
    # only one record on disk
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_retrieve_by_unique_prefix(tmp_path):
    res = ccr.compress(JSON_PAYLOAD, "json", cache_dir=tmp_path)
    sha = res["handle"][len(ccr.HANDLE_PREFIX):]
    assert ccr.retrieve("ccr://" + sha[:16], cache_dir=tmp_path) == JSON_PAYLOAD
    assert ccr.retrieve(sha[:16], cache_dir=tmp_path) == JSON_PAYLOAD  # bare prefix


def test_retrieve_missing_raises(tmp_path):
    try:
        ccr.retrieve("ccr://" + "0" * 64, cache_dir=tmp_path)
    except KeyError:
        pass
    else:
        raise AssertionError("missing handle must raise KeyError")


def test_short_prefix_rejected(tmp_path):
    ccr.compress(JSON_PAYLOAD, "json", cache_dir=tmp_path)
    try:
        ccr.retrieve("abc", cache_dir=tmp_path)  # < _MIN_PREFIX
    except KeyError:
        pass
    else:
        raise AssertionError("too-short prefix must raise KeyError")


def test_json_view_preserves_structure_not_data(tmp_path):
    res = ccr.compress(JSON_PAYLOAD, "json", cache_dir=tmp_path)
    view = res["view"]
    assert "str<" in view or "int" in view, "view should describe value types"
    assert "row-0" not in view, "view must NOT leak leaf data values"
    assert "200 items" in view, "view should note the elided collection size"


def test_code_view_lists_signatures(tmp_path):
    res = ccr.compress(CODE_PAYLOAD, "code", cache_dir=tmp_path)
    view = res["view"]
    assert "class Widget" in view
    assert "def render" in view
    assert "def make" in view
    assert "self.name = name" not in view, "bodies must be elided"


def test_text_view_keeps_head_and_tail(tmp_path):
    res = ccr.compress(TEXT_PAYLOAD, "text", cache_dir=tmp_path, head=3, tail=2)
    view = res["view"]
    assert "log line 0:" in view
    assert "log line 499:" in view
    assert "elided" in view
    assert "log line 250:" not in view, "middle must be elided"


def test_small_text_not_mangled(tmp_path):
    tiny = "one\ntwo\nthree"
    res = ccr.compress(tiny, "text", cache_dir=tmp_path)
    assert res["view"] == tiny, "payload below head+tail returns unchanged"


def test_stats_rollup(tmp_path):
    ccr.compress(JSON_PAYLOAD, "json", cache_dir=tmp_path)
    ccr.compress(TEXT_PAYLOAD, "text", cache_dir=tmp_path)
    s = ccr.stats(cache_dir=tmp_path)
    assert s["entries"] == 2
    assert s["original_chars"] > s["compact_chars"]
    assert 0 < s["cumulative_saved_pct"] < 100


def test_edge_payloads_roundtrip(tmp_path):
    # empty, unicode/emoji/RTL/4-byte/null-byte, lone surrogate, bare JSON scalars
    cases = [
        ("", "text"),
        ("café 🚀 مرحبا \x00 𝟙", "text"),
        ("\ud800", "text"),          # lone surrogate — must not crash (surrogatepass)
        ("42", "json"),
        ('"hi"', "json"),
        ("true", "json"),
        ("null", "json"),
        ("{}", "json"),
    ]
    for payload, ctype in cases:
        res = ccr.compress(payload, ctype, cache_dir=tmp_path)
        assert ccr.retrieve(res["handle"], cache_dir=tmp_path) == payload, f"{payload!r}"


def test_view_never_larger_than_original(tmp_path):
    # tiny inputs where a skeleton/marker would exceed the payload -> view==original
    for payload, ctype in [("{}", "json"), ("a\nb\nc\nd\ne\nf\ng\nh", "text")]:
        res = ccr.compress(payload, ctype, cache_dir=tmp_path)
        assert res["compact_chars"] <= res["original_chars"]
        assert res["saved_pct"] >= 0.0


def test_ambiguous_prefix_raises(tmp_path):
    # two cached records sharing an 8-char prefix -> retrieve(prefix) is ambiguous
    base = "a" * 8
    for suffix in ("0" * 56, "1" * 56):
        (tmp_path / f"{base}{suffix}.json").write_text(
            json.dumps({"original": "x", "content_type": "text",
                        "original_chars": 1, "compact_chars": 1})
        )
    try:
        ccr.retrieve(base, cache_dir=tmp_path)
    except KeyError as e:
        assert "ambiguous" in str(e)
    else:
        raise AssertionError("ambiguous prefix must raise KeyError")


def test_path_traversal_handle_is_rejected(tmp_path):
    ccr.compress("secret-bytes", "text", cache_dir=tmp_path)
    for evil in ("ccr://../../etc/passwd", "../../../../etc/passwd"):
        try:
            ccr.retrieve(evil, cache_dir=tmp_path)
        except KeyError:
            pass
        else:
            raise AssertionError(f"traversal handle must not resolve: {evil!r}")


def test_code_regex_no_catastrophic_backtracking(tmp_path):
    # long run of orphan decorator lines must not blow up _DEF_RE (ReDoS guard)
    import time
    payload = "@deco\n" * 20000 + "x = 1\n"
    t0 = time.time()
    ccr.compress(payload, "code", cache_dir=tmp_path)
    assert time.time() - t0 < 2.0, "compact_code regex is super-linear on decorator runs"


def test_unknown_content_type_raises(tmp_path):
    try:
        ccr.compress("x", "yaml", cache_dir=tmp_path)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown content_type must raise ValueError")


# --- no-pytest fallback runner ---------------------------------------------
if __name__ == "__main__":
    import tempfile
    import traceback

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for fn in fns:
        with tempfile.TemporaryDirectory() as d:
            try:
                fn(Path(d))
                passed += 1
                print(f"  ok   {fn.__name__}")
            except Exception:  # noqa: BLE001
                failed += 1
                print(f"  FAIL {fn.__name__}")
                traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
