#!/usr/bin/env python3
"""
test_ccr.py — unit tests for the ccr reversible-compression primitive (BRO-1521).

Run:
    python3 -m pytest skills/knowledge/ccr/tests/ -q
    # or, without pytest installed:
    python3 skills/knowledge/ccr/tests/test_ccr.py

The load-bearing invariant under test: the compact VIEW is lossy, but the
original is ALWAYS recoverable byte-for-byte via the handle (reversible-by-cache).
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

# Load the deterministic core from the sibling scripts/ dir (monorepo layout).
SCRIPT = Path(__file__).parent.parent / "scripts" / "ccr.py"
_spec = importlib.util.spec_from_file_location("ccr", SCRIPT)
ccr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ccr)


# --- CLI driver -------------------------------------------------------------
def _cli(args, cache_dir, stdin: bytes | None = None):
    """Drive the real CLI in a subprocess. Returns CompletedProcess of BYTES.

    PYTHONIOENCODING pins stdout to strict UTF-8 so the tests deterministically
    exercise the hostile configuration: under the C locale CPython silently
    installs a surrogateescape error handler on stdout and hides encoding bugs.
    """
    env = dict(
        os.environ, BROOMVA_CCR_HOME=str(cache_dir), PYTHONIOENCODING="utf-8"
    )
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin, capture_output=True, env=env,
    )


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

# Byte-level fixture matrix. NOT ONE of these existed before: the suite had no
# \r anywhere and never drove the CLI, which is exactly why universal-newline
# translation in _read_source went unnoticed while the docs claimed byte-exact.
BYTE_FIXTURES = {
    "crlf": b"alpha\r\nbeta\r\ngamma\r\n",
    "lone-cr": b"alpha\rbeta\rgamma",
    "mixed-eol": b"a\r\nb\nc\rd\r\n",
    "no-trailing-newline": b"alpha\nbeta\ngamma",
    "nul-byte": b"before\x00after\n",
    "utf8-bom-json": b'\xef\xbb\xbf{"k": [1, 2, 3]}',
    "four-byte-utf8": "emoji \U0001F680 astral \U0001D7D9 rtl مرحبا\n".encode(),
    "lone-surrogate-bytes": b"pre \xed\xa0\x80 post\n",
    "raw-non-utf8": b"latin \xff\xfe raw \x80\x81\n",
    "empty": b"",
    "crlf-past-elision": b"".join(b"row %d has content\r\n" % i for i in range(200)),
}


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
    """Assert compact_text DIRECTLY — never through compress().

    A compress()-level assertion here is green for a reason unrelated to its
    name: the `len(view) >= len(payload)` clamp inside compress() rescues a
    completely broken compactor, so deleting compact_text's early return still
    passed. Asserting the compactor itself is what makes the test able to fail.

    The trailing-newline and CRLF cases are the teeth: "\\n".join(splitlines())
    silently drops a trailing newline and normalises \\r\\n, so only returning
    `payload` verbatim can satisfy them.
    """
    for tiny in (
        "one\ntwo\nthree",
        "one\ntwo\nthree\n",      # trailing newline must survive
        "a\r\nb\r\n",             # CRLF must not be normalised
        "solo",
        "",
        "\n\n\n",
    ):
        assert ccr.compact_text(tiny) == tiny, f"compact_text mangled {tiny!r}"


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


def _plant_record(path: Path, marker: str) -> None:
    """Write a WELL-FORMED, digest-VALID record at `path`.

    Digest-valid on purpose: a bogus record would be rejected downstream by
    retrieve()'s digest check, which would mask whether the confinement layer
    under test actually did anything (the "green for an unrelated reason"
    failure mode this suite exists to avoid).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"sha256": ccr._digest(marker), "original": marker,
                                "content_type": "text",
                                "original_chars": len(marker), "compact_chars": 1}))


def _must_reject(fn, token, why):
    try:
        got = fn(token)
    except KeyError:
        return
    raise AssertionError(f"{why}: {token!r} resolved to {got!r}")


def _abs64_token(planted_marker):
    """An ABSOLUTE record token of exactly 64 chars, backed by a real record.

    Built under the shortest writable temp root: pytest's tmp_path is itself
    longer than 64 chars on most platforms, so the len(token)==64 fast path
    could not otherwise be reached with an absolute path. Returns (ctx, token)
    or (None, None) when no short-enough root exists.
    """
    if os.name != "posix":
        return None, None
    root = "/tmp" if os.path.isdir("/tmp") and os.access("/tmp", os.W_OK) \
        else tempfile.gettempdir()
    ctx = tempfile.TemporaryDirectory(dir=root)
    pad = 64 - len(ctx.name) - len("/") - len("/leak")
    if pad < 1:
        ctx.cleanup()
        return None, None
    _plant_record(Path(ctx.name) / ("z" * pad) / "leak.json", planted_marker)
    token = f"{ctx.name}/{'z' * pad}/leak"
    assert len(token) == 64 and Path(token + ".json").is_file()
    return ctx, token


def test_resolve_sha_never_returns_a_token_outside_the_cache(tmp_path):
    """Unit-level proof at the layer that was ACTUALLY vulnerable.

    The exploit was: `_resolve_sha`'s 64-char fast path returned the token
    unvalidated whenever `cache_dir / token` existed — and Path.__truediv__
    DISCARDS cache_dir for an absolute token and keeps `..` for a relative one
    — after which retrieve() read that path with no further checks.

    This is asserted on `_resolve_sha` directly, NOT only through retrieve():
    the digest check added downstream also refuses these tokens, so an
    end-to-end assertion alone stays green even with the validation deleted.
    """
    cache = tmp_path / "cache"
    cache.mkdir()
    _plant_record(tmp_path / "outside" / "leak.json", "LEAKED-VIA-TRAVERSAL")
    resolve = lambda t: ccr._resolve_sha(t, cache)  # noqa: E731

    # relative traversal of EXACTLY 64 chars, normalising to <cache>/../outside/leak
    rel64 = "../" + "./" * 24 + "/outside/leak"
    assert len(rel64) == 64
    assert (cache / (rel64 + ".json")).is_file(), \
        "fixture must genuinely reach the planted record"
    _must_reject(resolve, rel64, "64-char relative traversal")

    # absolute path of EXACTLY 64 chars, backed by a real record
    ctx, abs64 = _abs64_token("LEAKED-VIA-ABSOLUTE")
    if ctx is not None:
        try:
            assert (cache / (abs64 + ".json")).is_file(), "fixture must be reachable"
            _must_reject(resolve, abs64, "64-char absolute path token")
        finally:
            ctx.cleanup()

    # tokens that are not lowercase hex must never reach the filesystem at all
    for token in ("A" * 64, "g" * 64, "0" * 63 + "/", " " * 63 + "a", "0" * 65,
                  "0X" + "a" * 62, ""):
        _must_reject(resolve, token, "non-hex/oversized token")


def test_path_traversal_handle_is_rejected(tmp_path):
    """End-to-end composite: no escape shape survives retrieve().

    The old version only used tokens of length != 64 — i.e. only the prefix-scan
    branch, which was never vulnerable — so it passed against the exploitable
    code. The 64-char cases below are the ones that actually leaked.
    """
    cache = tmp_path / "cache"
    cache.mkdir()
    ccr.compress("secret-bytes", "text", cache_dir=cache)
    _plant_record(tmp_path / "outside" / "leak.json", "LEAKED-VIA-TRAVERSAL")
    retrieve = lambda t: ccr.retrieve(t, cache_dir=cache)  # noqa: E731

    _must_reject(retrieve, "ccr://../../etc/passwd", "traversal")
    _must_reject(retrieve, "../../../../etc/passwd", "traversal")
    _must_reject(retrieve, "../outside/leak", "short relative traversal")
    _must_reject(retrieve, str(tmp_path / "outside" / "leak"), "absolute token")
    _must_reject(retrieve, "../" + "./" * 24 + "/outside/leak", "64-char relative")
    _must_reject(retrieve, "ccr://" + "../" + "./" * 24 + "/outside/leak",
                 "64-char relative behind the ccr:// prefix")

    ctx, abs64 = _abs64_token("LEAKED-VIA-ABSOLUTE")
    if ctx is not None:
        try:
            _must_reject(retrieve, abs64, "64-char absolute token")
        finally:
            ctx.cleanup()


def test_symlinked_cache_record_is_rejected(tmp_path):
    """A symlink planted in the cache dir must not be read through.

    Hex validation does not close this: `<sha>.json` is a perfectly valid name
    and can still be a symlink to anywhere. The planted record is deliberately
    DIGEST-VALID (its sha256 IS the filename), so the digest check cannot be
    what rejects it — only the symlink/confinement check can.
    """
    cache = tmp_path / "cache"
    cache.mkdir()
    secret = "LEAKED-VIA-SYMLINK"
    sha = ccr._digest(secret)
    _plant_record(tmp_path / "elsewhere.json", secret)
    (cache / f"{sha}.json").symlink_to(tmp_path / "elsewhere.json")

    _must_reject(lambda t: ccr.retrieve(t, cache_dir=cache), sha, "symlinked record")
    _must_reject(lambda t: ccr._resolve_sha(t, cache), sha, "symlinked record")
    # and the prefix-scan branch must not surface it either
    _must_reject(lambda t: ccr.retrieve(t, cache_dir=cache), sha[:16],
                 "symlinked record via prefix")


def test_code_regex_no_catastrophic_backtracking(tmp_path):
    """Both code regexes must stay linear.

    The old test only covered _DEF_RE (already correct: `[ \\t]*`). _IMPORT_RE
    used `^\\s*`, and \\s matches \\n — so at every one of N line starts the
    engine ran to EOF over the whitespace run and backtracked. Measured before
    the fix: 32KB of blank lines = 5.6s, 64KB = 26s, quadratic.
    """
    # (a) _DEF_RE: long run of orphan decorator lines
    payload = "@deco\n" * 20000 + "x = 1\n"
    t0 = time.time()
    ccr.compress(payload, "code", cache_dir=tmp_path)
    assert time.time() - t0 < 2.0, "_DEF_RE is super-linear on decorator runs"

    # (b) _IMPORT_RE: an import followed by a long whitespace run. Blank lines
    # are excluded from the code-density denominator, so `auto` routes this to
    # the code compactor — the ReDoS is reachable without an explicit --type.
    blank_run = "import x\n" + "\n" * 32768
    assert ccr.detect_type(blank_run) == "code", "fixture must reach compact_code"
    t0 = time.time()
    ccr.compress(blank_run, "auto", cache_dir=tmp_path)
    assert time.time() - t0 < 2.0, "_IMPORT_RE is super-linear on whitespace runs"


def test_unknown_content_type_raises(tmp_path):
    try:
        ccr.compress("x", "yaml", cache_dir=tmp_path)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown content_type must raise ValueError")


# --- byte-exactness THROUGH THE CLI ----------------------------------------
# The Python API round-trip was already covered; the CLI was not covered at
# all, and the CLI is where byte-exactness was false: Path.read_text() applies
# universal-newline translation BEFORE hashing, so \r\n and lone \r became \n
# and the original bytes were gone for good.
def test_cli_round_trip_is_byte_exact_over_fixture_matrix(tmp_path):
    cache = tmp_path / "cache"
    for name, raw in BYTE_FIXTURES.items():
        src = tmp_path / f"{name}.bin"
        src.write_bytes(raw)
        out = _cli(["compress", str(src), "--json"], cache)
        assert out.returncode == 0, f"{name}: compress failed: {out.stderr!r}"
        handle = json.loads(out.stdout)["handle"]
        back = _cli(["retrieve", handle], cache)
        assert back.returncode == 0, f"{name}: retrieve failed: {back.stderr!r}"
        assert back.stdout == raw, (
            f"{name}: CLI round trip is NOT byte-exact\n"
            f"  in : {raw!r}\n  out: {back.stdout!r}"
        )


def test_cli_stdin_round_trip_is_byte_exact(tmp_path):
    cache = tmp_path / "cache"
    for name in ("crlf", "lone-cr", "raw-non-utf8", "nul-byte"):
        raw = BYTE_FIXTURES[name]
        out = _cli(["compress", "-", "--json"], cache, stdin=raw)
        assert out.returncode == 0, f"{name}: {out.stderr!r}"
        handle = json.loads(out.stdout)["handle"]
        back = _cli(["retrieve", handle], cache)
        assert back.stdout == raw, f"{name}: stdin round trip not byte-exact"


def test_cli_handle_matches_the_real_bytes(tmp_path):
    """The handle is the sha256 of the FILE'S BYTES, not of a translated copy.

    Guards the failure directly: with newline translation, a CRLF file and its
    LF twin collide on one handle, so retrieve() could not possibly return both.
    """
    cache = tmp_path / "cache"
    crlf, lf = tmp_path / "crlf.txt", tmp_path / "lf.txt"
    crlf.write_bytes(b"a\r\nb\r\n")
    lf.write_bytes(b"a\nb\n")
    h_crlf = json.loads(_cli(["compress", str(crlf), "--json"], cache).stdout)["handle"]
    h_lf = json.loads(_cli(["compress", str(lf), "--json"], cache).stdout)["handle"]
    assert h_crlf != h_lf, "CRLF and LF files must not collide on one handle"
    import hashlib
    assert h_crlf == ccr.HANDLE_PREFIX + hashlib.sha256(b"a\r\nb\r\n").hexdigest()


def test_digest_domain_is_collision_free(tmp_path):  # tmp_path unused; keeps the
                                                     # no-pytest runner's arity
    """The digest is taken over the DECODED payload via surrogatepass.

    Consequence, documented rather than accidental: for valid-UTF-8 input the
    handle IS sha256(bytes); for non-UTF-8 input it is not, because the payload
    is addressed by its surrogateescape-decoded form.

    Switching the digest to surrogateescape (which would make handle ==
    sha256(bytes) universally) is NOT safe: it maps two distinct payloads onto
    one handle, and with digest verification in place the wrong one would
    verify. This test pins that reasoning so the trade is not silently undone.
    """
    import hashlib
    for raw in (b"a\r\nb\r\n", b"\xef\xbb\xbfbom\x00nul \xf0\x9f\x9a\x80"):
        text = raw.decode("utf-8", "surrogateescape")
        assert ccr._digest(text) == hashlib.sha256(raw).hexdigest(), \
            "valid UTF-8 must be addressed by its exact bytes"

    api_lone_surrogate = "\ud800"              # via the Python API
    file_bytes_ed_a0_80 = "\udced\udca0\udc80"  # a file holding ED A0 80
    assert ccr._encode_out(api_lone_surrogate) == ccr._encode_out(file_bytes_ed_a0_80), \
        "fixture: these two DO share an output encoding"
    assert ccr._digest(api_lone_surrogate) != ccr._digest(file_bytes_ed_a0_80), \
        "distinct payloads must never share a handle"


def test_cli_view_output_survives_non_utf8_payloads(tmp_path):
    """The non---json view path writes BYTES, not locale-encoded text.

    Accepting non-UTF-8 input (surrogateescape) put lone surrogates into the
    VIEW; print() encodes stdout strictly and died with UnicodeEncodeError.
    """
    cache = tmp_path / "cache"
    src = tmp_path / "bin.log"
    src.write_bytes(b"noise \xff\xfe more \x80\x81 bytes\n")
    out = _cli(["compress", str(src)], cache)
    assert out.returncode == 0, f"view path crashed: {out.stderr!r}"
    assert b"\xff\xfe" in out.stdout, "view must carry the raw bytes through"


def test_cli_json_envelope_is_always_parseable(tmp_path):
    """--json is a MACHINE envelope: pure ASCII, decodable by any JSON reader."""
    cache = tmp_path / "cache"
    src = tmp_path / "bin.log"
    src.write_bytes(BYTE_FIXTURES["raw-non-utf8"] + BYTE_FIXTURES["four-byte-utf8"])
    out = _cli(["compress", str(src), "--json"], cache)
    assert out.returncode == 0, out.stderr
    out.stdout.decode("ascii")            # must not raise
    json.loads(out.stdout)                # must not raise


def test_cli_rejects_malformed_handles(tmp_path):
    cache = tmp_path / "cache"
    src = tmp_path / "a.txt"
    src.write_bytes(b"content\n")
    _cli(["compress", str(src)], cache)
    for evil in ("../../etc/passwd", "/etc/passwd", "ZZZZ" * 16, "ccr://" + "!" * 64):
        r = _cli(["retrieve", evil], cache)
        assert r.returncode == 1, f"{evil!r}: expected exit 1, got {r.returncode}"
        assert r.stdout == b"", f"{evil!r}: leaked {r.stdout!r}"


# --- cache integrity: atomic on write, verified on read ---------------------
def test_record_is_published_atomically(tmp_path):
    """The canonical record path is only ever created by an atomic rename.

    Path.write_text streams into the final name, so a concurrent reader sees a
    half-written record (measured: 235 torn reads during one 60MB write). This
    asserts the mechanism deterministically: if publishing fails, NO record is
    left at the canonical path.
    """
    real_replace = ccr.os.replace
    calls = []

    def failing_replace(src, dst):
        calls.append((src, dst))
        raise OSError("simulated crash mid-publish")

    ccr.os.replace = failing_replace
    try:
        try:
            ccr.compress("payload-under-test", "text", cache_dir=tmp_path)
        except OSError:
            pass
    finally:
        ccr.os.replace = real_replace

    assert calls, "records must be published via os.replace (temp file + rename)"
    assert not list(tmp_path.glob("*.json")), \
        "a failed publish must leave NO record at the canonical path"


def test_concurrent_reader_never_observes_a_torn_record(tmp_path):
    """Empirical counterpart to the test above: race a real external reader."""
    cache = tmp_path / "cache"
    cache.mkdir()
    sentinel = tmp_path / "DONE"
    reader = tmp_path / "reader.py"
    reader.write_text(textwrap.dedent("""
        import json, sys, time
        from pathlib import Path
        cache, sentinel = Path(sys.argv[1]), Path(sys.argv[2])
        torn, deadline = 0, time.time() + 60
        while not sentinel.exists() and time.time() < deadline:
            for p in cache.glob("*.json"):
                try:
                    json.loads(p.read_text(encoding="utf-8"))
                except (ValueError, OSError):
                    torn += 1
        print(torn)
    """))
    proc = subprocess.Popen(
        [sys.executable, str(reader), str(cache), str(sentinel)],
        stdout=subprocess.PIPE, text=True,
    )
    try:
        time.sleep(0.3)                       # let the reader spin up
        ccr.compress("x" * (16 * 1024 * 1024), "text", cache_dir=cache)
    finally:
        sentinel.touch()
    torn = int(proc.communicate(timeout=90)[0].strip())
    assert torn == 0, f"reader observed {torn} torn records mid-write"


def test_retrieve_verifies_the_digest(tmp_path):
    """A content-addressed store that serves unverified bytes is not one."""
    res = ccr.compress("honest-content", "text", cache_dir=tmp_path)
    sha = res["handle"][len(ccr.HANDLE_PREFIX):]
    rec_path = tmp_path / f"{sha}.json"
    rec = json.loads(rec_path.read_text())
    rec["original"] = "TAMPERED-CONTENT"
    rec_path.write_text(json.dumps(rec))
    try:
        got = ccr.retrieve(res["handle"], cache_dir=tmp_path)
    except KeyError:
        pass
    else:
        raise AssertionError(f"tampered record must not be served (got {got!r})")


def test_unusable_record_self_heals_instead_of_being_cemented(tmp_path):
    """compress() short-circuited on exists(), so a partial record was FOREVER.

    Both corruption shapes (truncated and tampered) must be overwritten by the
    next compress of the same payload, and retrievable afterwards.
    """
    payload = "will-be-corrupted"
    res = ccr.compress(payload, "text", cache_dir=tmp_path)
    sha = res["handle"][len(ccr.HANDLE_PREFIX):]
    rec_path = tmp_path / f"{sha}.json"

    for corruption in ('{"sha256": "' + sha + '", "orig',            # truncated
                       json.dumps({"original": "TAMPERED"})):        # wrong bytes
        rec_path.write_text(corruption)
        ccr.compress(payload, "text", cache_dir=tmp_path)            # self-heal
        assert ccr.retrieve(res["handle"], cache_dir=tmp_path) == payload, \
            f"store did not heal from {corruption[:24]!r}"


def test_cache_is_not_world_readable(tmp_path):
    """The cache holds full plaintext originals; 0755/0644 leaks them locally."""
    cache = tmp_path / "cache"
    old_umask = os.umask(0)      # pin umask so the assertion is runner-independent
    try:
        ccr.compress("private-bytes", "text", cache_dir=cache)
    finally:
        os.umask(old_umask)
    assert stat.S_IMODE(cache.stat().st_mode) == 0o700, "cache dir must be 0700"
    rec = next(cache.glob("*.json"))
    assert stat.S_IMODE(rec.stat().st_mode) == 0o600, "records must be 0600"

    # a cache dir left loose by an older version is tightened on the next
    # compress, even when that compress is a pure cache HIT and writes nothing
    os.chmod(cache, 0o755)
    ccr.compress("private-bytes", "text", cache_dir=cache)
    assert stat.S_IMODE(cache.stat().st_mode) == 0o700, "loose cache dir not tightened"


def test_no_temp_files_leak_into_the_record_namespace(tmp_path):
    for i in range(5):
        ccr.compress(f"payload-{i}", "text", cache_dir=tmp_path)
    names = sorted(p.name for p in tmp_path.iterdir())
    assert len(names) == 5, f"stray files in cache: {names}"
    assert all(re.fullmatch(r"[0-9a-f]{64}\.json", n) for n in names), names


# --- character budget: the single-line-blob case ---------------------------
def test_single_line_blob_is_compressed_by_char_budget(tmp_path):
    """compact_text was purely line-oriented, so a one-line blob saved 0%."""
    blob = "x" * 400_000
    res = ccr.compress(blob, "text", cache_dir=tmp_path)
    assert res["saved_pct"] > 90, f"single-line blob saved only {res['saved_pct']}%"
    assert res["compact_chars"] < ccr.LINE_CHAR_BUDGET + 200
    assert ccr.retrieve(res["handle"], cache_dir=tmp_path) == blob


def test_truncated_json_blob_is_compressed(tmp_path):
    """The most common large tool output: streamed/truncated JSON on one line.

    detect_type needs a SUCCESSFUL json.loads, so a truncated document routes
    to text — which, being line-oriented, returned all 1.2MB as the view.
    """
    payload = '[{"a":1,"b":2}' * 20_000
    res = ccr.compress(payload, "auto", cache_dir=tmp_path)
    assert res["content_type"] == "text"
    assert res["saved_pct"] > 90, f"truncated json saved only {res['saved_pct']}%"
    assert ccr.retrieve(res["handle"], cache_dir=tmp_path) == payload


def test_char_budget_marks_what_it_dropped(tmp_path):
    line = "y" * 50_000
    view = ccr.compact_text(line)
    m = re.search(r"\[… (-?\d+) chars elided[^\]]*\]", view)
    assert m, f"over-long line must be marked as elided: {view[:120]!r}"
    dropped = int(m.group(1))
    kept = len(view) - len(m.group(0))
    assert dropped > 0
    assert dropped == len(line) - kept, f"count lies: {dropped} vs {len(line) - kept}"


def test_char_budget_is_tunable_and_disableable(tmp_path):
    line = "z" * 10_000
    assert len(ccr.compact_text(line, line_budget=500)) < 700
    assert ccr.compact_text(line, line_budget=0) == line, "0 disables the budget"


# --- head/tail bounds -------------------------------------------------------
def test_head_tail_bounds_are_clamped_and_elision_count_is_honest(tmp_path):
    """`--tail 0` silently disabled compression (`lines[-0:]` is everything),
    and negative bounds produced a view LARGER than the original with a
    misreported elision count (19354 misreporting (n, head, tail) combos).
    """
    text = "\n".join(f"line {i}" for i in range(500))
    res = ccr.compress(text, "text", cache_dir=tmp_path, head=5, tail=0)
    assert res["saved_pct"] > 90, "tail=0 must still compress"
    assert "line 499" not in res["view"], "tail=0 must keep NO tail lines"
    assert "line 4" in res["view"] and "line 250" not in res["view"]

    # exhaustive: over a grid of bounds the view must never carry MORE lines
    # than it started with (negative bounds made `lines[:head]` and
    # `lines[-tail:]` overlap, duplicating most of the payload), and the marker
    # must never lie. Line count, not char count: for a tiny payload the marker
    # alone is legitimately longer than the input, which is why compress()
    # keeps its own `len(view) >= len(payload)` clamp on top.
    for n in (0, 1, 5, 12, 31, 60):
        payload = "\n".join(f"L{i}" for i in range(n))
        for head in range(-6, 7):
            for tail in range(-6, 7):
                view = ccr.compact_text(payload, head=head, tail=tail)
                assert len(view.splitlines()) <= n + 1, \
                    f"view grew: n={n} head={head} tail={tail}"
                m = re.search(r"\[… (-?\d+) lines elided", view)
                if not m:
                    continue
                claimed = int(m.group(1))
                actual = len(payload.splitlines()) - (len(view.splitlines()) - 1)
                assert claimed >= 0, f"negative elision count: n={n} {head=} {tail=}"
                assert claimed == actual, (
                    f"elision count lies: n={n} {head=} {tail=} "
                    f"claimed={claimed} actual={actual}"
                )


# --- deep nesting -----------------------------------------------------------
def test_deeply_nested_json_never_escapes_as_recursion_error(tmp_path):
    """_shape capped dict depth but NOT list depth, so `[[[[…]]]]` blew the
    stack and RecursionError escaped compress() -> CLI exit 2.
    """
    for payload in ("[" * 1200 + "]" * 1200, '{"a":' * 400 + "1" + "}" * 400):
        res = ccr.compress(payload, "auto", cache_dir=tmp_path)  # must not raise
        assert ccr.retrieve(res["handle"], cache_dir=tmp_path) == payload

    # past the PARSER's own depth limit, auto must degrade to text, not explode
    monster = "[" * 100_000 + "]" * 100_000
    assert ccr.compress(monster, "auto", cache_dir=tmp_path)["content_type"] == "text"


def test_cli_maps_over_deep_json_to_a_user_error_not_an_internal_one(tmp_path):
    cache = tmp_path / "cache"
    monster = ("[" * 100_000 + "]" * 100_000).encode()
    r = _cli(["compress", "-", "--type", "json"], cache, stdin=monster)
    assert r.returncode == 1, f"expected exit 1 (bad payload), got {r.returncode}"
    r_auto = _cli(["compress", "-", "--type", "auto"], cache, stdin=monster)
    assert r_auto.returncode == 0, f"auto must degrade: {r_auto.stderr!r}"


# --- BOM --------------------------------------------------------------------
def test_bom_does_not_defeat_json_detection(tmp_path):
    payload = "﻿" + json.dumps({"k": [1, 2, 3], "n": {"a": "b"}})
    assert ccr.detect_type(payload) == "json", "a BOM must not hide the JSON"
    # content_type == json also proves compact_json PARSED it (it would raise
    # ValueError out of compress() otherwise).
    res = ccr.compress(payload, "auto", cache_dir=tmp_path)
    assert res["content_type"] == "json"
    assert ccr.retrieve(res["handle"], cache_dir=tmp_path) == payload, \
        "the BOM must survive in the cached original"


# --- no-pytest fallback runner ---------------------------------------------
# ── Gaps proven by surviving mutations in P20 round 2 ─────────────────────────
#
# Round-2 verification mutated 27 sites; 20 were caught. Four survivors were
# classified VACUOUS (a guard no test could fail on) rather than EQUIVALENT (a
# mutation that changes no observable behaviour — `os.chmod(0600)` on a
# NamedTemporaryFile is one, since the file is already 0600; that one is
# correctly NOT tested here).
#
# None of the four was a security hole — traversal stayed refused throughout,
# because each guard is backed by a second, independent one. What was missing
# was coverage: delete a guard, and the suite stayed green on the strength of
# its neighbour. These pin each guard on its own.


def test_malformed_handle_is_refused_BEFORE_the_filesystem_is_touched(tmp_path):
    """Kills M1 — pins the ORDERING, which is the part the docs claim.

    A first attempt at this test planted a non-hex record in the cache and
    asserted `retrieve` raised. It passed with the hex check DELETED, because
    the digest verification rejected the planted record anyway. That is the
    same defence-in-depth cover one layer deeper, and it is why "the mutation
    survived" was the right thing to chase rather than explain away.

    The ordering is only observable when the two guards would give DIFFERENT
    answers. Point the cache at a directory that does not exist: with
    validation first, a malformed token yields "malformed handle"; without it,
    execution reaches the filesystem check and yields "no ccr cache". Asserting
    on WHICH error distinguishes them.
    """
    missing_cache = tmp_path / "does-not-exist"
    assert not missing_cache.exists()
    try:
        ccr.retrieve("ccr://" + "N" * 64, cache_dir=missing_cache)
    except KeyError as e:
        assert "malformed handle" in str(e), (
            f"reached the filesystem before validating the handle: {e}"
        )
    else:
        raise AssertionError("a malformed handle must raise")


def test_symlink_whose_target_is_inside_the_cache_is_rejected(tmp_path):
    """A symlinked record is refused even when its target is INSIDE the cache.

    Honest scope note: this does NOT kill the `is_symlink()` mutation. Delete
    that guard and this still passes, because the digest check refuses the
    record anyway — a symlink can only ever serve content whose sha256 matches
    the requested handle, and no content hashes to the link's own name.

    That makes `if p.is_symlink()` an EQUIVALENT MUTANT under the current
    design (defence-in-depth with no reachable behavioural difference), not an
    untested guard. The distinction matters: writing a contrived test to force
    it red would be manufacturing coverage rather than measuring it. The test
    is kept because it pins the observable contract — symlinked records are
    refused — which is what a caller depends on.
    """
    res = ccr.compress(TEXT_PAYLOAD, "text", cache_dir=tmp_path)
    real_sha = res["handle"].removeprefix("ccr://")
    link_sha = "b" * 64
    link = tmp_path / f"{link_sha}.json"
    link.symlink_to(tmp_path / f"{real_sha}.json")
    assert link.resolve().is_relative_to(tmp_path.resolve()), (
        "fixture guard: the target must be INSIDE the cache, or containment "
        "would reject it and this test would pass vacuously"
    )
    try:
        ccr.retrieve("ccr://" + link_sha, cache_dir=tmp_path)
    except KeyError:
        pass
    else:
        raise AssertionError("a symlinked record must be refused even when its "
                             "target is inside the cache")


def test_failed_publish_leaves_no_temp_file(tmp_path):
    """Kills M5b — the temp-file cleanup on a failed publish was untested.

    The existing atomicity test globs `*.json`, and a leaked temp file is named
    `.ccr-tmp-*.part`, so it was invisible. This is also the direct cause of
    the leaked-`.part`-on-SIGKILL defect.
    """
    def boom(*a, **k):
        raise OSError("publish failed")

    real_replace = ccr.os.replace
    ccr.os.replace = boom
    try:
        ccr.compress(TEXT_PAYLOAD, "text", cache_dir=tmp_path)
    except OSError:
        pass
    else:
        raise AssertionError("a failed publish must propagate")
    finally:
        ccr.os.replace = real_replace
    leaked = [p.name for p in tmp_path.iterdir() if not p.name.endswith(".json")]
    assert leaked == [], f"temp file leaked after a failed publish: {leaked}"


def test_prefix_scan_ignores_non_64_char_stems(tmp_path):
    """Kills M17 — the `len(stem) == 64` guard on the prefix scan was untested."""
    ccr.compress(TEXT_PAYLOAD, "text", cache_dir=tmp_path)
    (tmp_path / "deadbeef12.json").write_text(
        json.dumps({"original": "PLANTED", "sha256": "deadbeef12"})
    )
    try:
        ccr.retrieve("deadbeef", cache_dir=tmp_path)
    except KeyError:
        pass
    else:
        raise AssertionError("the prefix scan must ignore non-64-char stems")


def test_minified_code_line_respects_the_char_budget(tmp_path):
    """MAJOR 6 survived on the `code` path: `compact_code(payload, **_)`
    swallowed `line_budget`, so a minified JS/TS bundle — one enormous line
    that still matches `_DEF_RE` — compressed to exactly 0.0%."""
    minified = "function f(){" + ("a;" * 100_000) + "}"
    res = ccr.compress(minified, "auto", cache_dir=tmp_path)
    assert res["content_type"] == "code", "fixture guard: must route to compact_code"
    assert res["saved_pct"] > 90.0, f"still 0%-ish on the code path: {res['saved_pct']}"
    assert len(res["view"]) < len(minified)
    assert ccr.retrieve(res["handle"], cache_dir=tmp_path) == minified


def test_code_fallback_carries_the_callers_budgets(tmp_path):
    """`compact_code`'s no-structure fallback called `compact_text(payload)`
    with DEFAULTS, silently discarding whatever the caller asked for."""
    prose_like_code = "import x\n" + "\n".join(f"line {i}" for i in range(500))
    tight = ccr.compress(prose_like_code, "code", cache_dir=tmp_path, head=1, tail=1)
    loose = ccr.compress(prose_like_code, "code", cache_dir=tmp_path, head=100, tail=100)
    assert len(tight["view"]) < len(loose["view"]), (
        "head/tail had no effect through the code path — args were dropped"
    )


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

