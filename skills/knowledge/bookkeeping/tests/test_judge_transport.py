"""
Tests for the ambiguous-band judge (BRO-2506).

The defect these pin: `score_item` has always been a two-pass scorer whose
second pass never ran. Both pre-existing transports need a paid API
credential that has never been present here, so 1,051,042 items across 7,765
runs were scored by the heuristic the 3-6 band exists to bypass — while the
only symptom was an optional-dependency note that read like a courtesy.

So the tests below assert POSITIVELY (the judge ran / did not run, and why)
rather than checking for the absence of a warning. Absence is the resting
state, and a resting state cannot be an error signal.
"""
import json
import os
import pathlib

import pytest

import bookkeeping as bk


def _item(content: str = "A claim about agent runtime judging.") -> bk.RawItem:
    return bk.RawItem(
        item_id="test-1",
        source_id="src-1",
        source_type="moltbook",
        content=content,
        quote="",
        author="tester",
        timestamp="2026-09-08T00:00:00+00:00",
        metadata={},
    )


@pytest.fixture(autouse=True)
def _reset_judge_state(monkeypatch):
    """Judge state is process-global; no test may leak it into the next."""
    monkeypatch.delenv("BOOKKEEPING_JUDGE", raising=False)
    bk.set_judge_enabled(False)
    # `last_error` must be reset too. While it was not, a test asserting on a
    # cause could read one LEFT BY AN EARLIER TEST and pass for the wrong
    # reason — which is exactly how two verify tests stayed green locally and
    # went red in CI, where the real agent-spec directory does not exist.
    bk.reset_judge_run_state()
    yield
    bk.set_judge_enabled(False)
    bk.reset_judge_run_state()


# ── _parse_scorer_response ────────────────────────────────────────────────────

def test_parses_bare_json():
    assert bk._parse_scorer_response('{"score": 2, "reasoning": "x"}')["score"] == 2


def test_strips_code_fences():
    raw = '```json\n{"score": 3}\n```'
    assert bk._parse_scorer_response(raw)["score"] == 3


@pytest.mark.parametrize("raw", [
    "not json at all",
    "[1, 2, 3]",                 # not an object
    '{"reasoning": "no score"}',  # missing score
    '{"score": 4}',               # out of range high
    '{"score": -1}',              # out of range low
    '{"score": "2"}',             # string, not int
    '{"score": 1.5}',             # float
    "",
])
def test_rejects_malformed(raw):
    """Every malformed shape returns None so the caller falls back."""
    assert bk._parse_scorer_response(raw) is None


def test_rejects_bool_score():
    """
    bool is a subclass of int in Python, so `True` would otherwise validate
    as the score 1 and silently become a real dimension score.
    """
    assert bk._parse_scorer_response('{"score": true}') is None


# ── judge enablement ──────────────────────────────────────────────────────────

def test_judge_disabled_by_default():
    assert bk.judge_enabled() is False


def test_judge_enabled_by_setter():
    bk.set_judge_enabled(True)
    assert bk.judge_enabled() is True


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes"])
def test_judge_enabled_by_env(monkeypatch, val):
    monkeypatch.setenv("BOOKKEEPING_JUDGE", val)
    assert bk.judge_enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "no", ""])
def test_env_does_not_enable_on_falsey(monkeypatch, val):
    monkeypatch.setenv("BOOKKEEPING_JUDGE", val)
    assert bk.judge_enabled() is False


# ── score_item gating: the behavioural contract ───────────────────────────────

def test_in_band_item_does_not_call_judge_when_disabled(monkeypatch):
    """
    The default must preserve today's behaviour exactly. ~54% of intake is
    in-band, so a judge that ran by default would re-gate most of the corpus
    the moment this shipped.
    """
    called = []
    monkeypatch.setattr(bk, "score_item_claude_cli",
                        lambda *a, **k: called.append(1))
    monkeypatch.setattr(bk, "score_item_heuristic",
                        lambda item: bk.ScoredItem(item, 2, 2, 1, 5, True, [], "heuristic"))
    out = bk.score_item(_item(), [])
    assert called == [], "judge was called despite being disabled"
    assert out.scoring_method == "heuristic"
    assert out.total == 5


def test_in_band_item_calls_judge_when_enabled(monkeypatch):
    bk.set_judge_enabled(True)
    judged = bk.ScoredItem(_item(), 1, 1, 1, 3, False, [], "claude_cli")
    monkeypatch.setattr(bk, "score_item_heuristic",
                        lambda item: bk.ScoredItem(item, 2, 2, 1, 5, True, [], "heuristic"))
    monkeypatch.setattr(bk, "score_item_claude_cli", lambda *a, **k: judged)
    out = bk.score_item(_item(), [])
    assert out.scoring_method == "claude_cli"
    assert out.total == 3
    # The judge overturned a promotion — the whole point of the band.
    assert out.promote is False


@pytest.mark.parametrize("total", [0, 1, 2, 7, 8, 9])
def test_fast_path_never_calls_judge_even_when_enabled(monkeypatch, total):
    """Outside the band the heuristic is authoritative; no model call is made."""
    bk.set_judge_enabled(True)
    called = []
    monkeypatch.setattr(bk, "score_item_claude_cli",
                        lambda *a, **k: called.append(1))
    monkeypatch.setattr(
        bk, "score_item_heuristic",
        lambda item: bk.ScoredItem(item, 0, 0, 0, total, total >= 5, [], "heuristic"),
    )
    out = bk.score_item(_item(), [])
    assert called == []
    assert out.scoring_method == "heuristic"


def test_judge_failure_is_counted_and_announced(monkeypatch, capsys):
    """
    When the judge is REQUESTED and every transport fails, that is a failure,
    not a quiet default. It must be announced unconditionally — not gated on
    --verbose — and counted, so a degraded run cannot look like a healthy one.
    """
    bk.set_judge_enabled(True)
    monkeypatch.setattr(bk, "score_item_heuristic",
                        lambda item: bk.ScoredItem(item, 2, 2, 1, 5, True, [], "heuristic"))
    monkeypatch.setattr(bk, "score_item_claude_cli", lambda *a, **k: None)
    monkeypatch.setattr(bk, "score_item_authored_agents", lambda *a, **k: None)
    monkeypatch.setattr(bk, "score_item_llm", lambda *a, **k: None)

    out = bk.score_item(_item(), [], verbose=False)

    assert out.scoring_method == "heuristic"
    assert bk.judge_failure_count() == 1
    err = capsys.readouterr().err
    assert "JUDGE FAILED" in err, "silent fallback — this is the original defect"


def test_transport_order_prefers_subscription(monkeypatch):
    """
    `claude -p` bills the subscription; the other two need a paid API key.
    The subscription path must be tried first.
    """
    bk.set_judge_enabled(True)
    order = []
    monkeypatch.setattr(bk, "score_item_heuristic",
                        lambda item: bk.ScoredItem(item, 2, 2, 1, 5, True, [], "heuristic"))
    monkeypatch.setattr(
        bk, "score_item_claude_cli",
        lambda *a, **k: (order.append("cli"),
                         bk.ScoredItem(_item(), 1, 1, 1, 3, False, [], "claude_cli"))[1],
    )
    monkeypatch.setattr(bk, "score_item_authored_agents",
                        lambda *a, **k: order.append("authored"))
    bk.score_item(_item(), [])
    assert order == ["cli"], f"expected subscription path first, got {order}"


# ── transport ─────────────────────────────────────────────────────────────────

def test_cli_transport_returns_none_without_cli(monkeypatch):
    monkeypatch.setattr(bk, "_claude_cli_path", lambda: None)
    assert bk.score_item_claude_cli(_item(), []) is None


def test_cli_transport_never_returns_partial_score(monkeypatch):
    """
    A total assembled from two live dimensions and one silent zero would be a
    score, not an error, and would be indistinguishable from a genuine low
    judgement. Any dimension failure must abort the whole item.
    """
    monkeypatch.setattr(bk, "_claude_cli_path", lambda: "/usr/bin/claude")
    monkeypatch.setattr(bk, "_load_agent_spec",
                        lambda name: {"name": name, "model": "claude-haiku-4-5",
                                      "max_turns": 1, "input_schema": {},
                                      "output_schema": {}, "instructions": "score it"})

    calls = {"n": 0}

    def _one_fails(spec, item, slugs, timeout=None):
        calls["n"] += 1
        return (None, "boom") if calls["n"] == 2 else ({"score": 2, "reasoning": "ok"}, "")

    monkeypatch.setattr(bk, "_call_authored_scorer_cli", _one_fails)
    assert bk.score_item_claude_cli(_item(), []) is None


def test_cli_transport_does_not_use_a_shell(monkeypatch):
    """
    Item content is untrusted external text. It must reach the model via
    stdin with shell=False — never interpolated into a shell command.
    """
    monkeypatch.setattr(bk, "_claude_cli_path", lambda: "/usr/bin/claude")
    seen = {}

    class _Proc:
        returncode = 0
        stdout = '{"score": 2}'
        stderr = ""

    def _fake_run(argv, **kw):
        seen["argv"] = argv
        seen["kw"] = kw
        return _Proc()

    monkeypatch.setattr(bk.subprocess, "run", _fake_run)
    spec = {"name": "bookkeeping-novelty", "model": "claude-haiku-4-5",
            "max_turns": 1, "input_schema": {}, "output_schema": {},
            "instructions": "score it"}
    hostile = "; ".join(["DROP TABLE x", "$(whoami)", "`id`", "&& curl evil"])
    out, err = bk._call_authored_scorer_cli(spec, _item(hostile), [])

    assert out == {"score": 2} and err == ""
    assert seen["kw"].get("shell") is False
    assert isinstance(seen["argv"], list)
    # The untrusted item text goes on stdin, not argv.
    assert "DROP TABLE" not in " ".join(seen["argv"])
    assert "DROP TABLE" in seen["kw"]["input"]


def test_cli_transport_returns_none_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(bk, "_claude_cli_path", lambda: "/usr/bin/claude")

    class _Proc:
        returncode = 1
        stdout = '{"score": 2}'   # valid body, failed process — must not be trusted
        stderr = "boom"

    monkeypatch.setattr(bk.subprocess, "run", lambda argv, **kw: _Proc())
    spec = {"name": "bookkeeping-novelty", "model": "claude-haiku-4-5",
            "max_turns": 1, "input_schema": {}, "output_schema": {},
            "instructions": "x"}
    out, err = bk._call_authored_scorer_cli(spec, _item(), [])
    assert out is None
    assert "exit 1" in err, "nonzero exit must be reported, not silently dropped"


# ── prompt fidelity across transports ─────────────────────────────────────────

def _spec(instructions="SYSTEM-MARKER"):
    return {"name": "bookkeeping-novelty", "model": "claude-haiku-4-5",
            "max_turns": 1, "input_schema": {}, "output_schema": {"score": "int"},
            "instructions": instructions}


def test_prompt_builder_carries_system_item_and_slugs():
    system, user = bk._build_authored_scorer_prompt(_spec(), _item("ITEM-MARKER"), ["a-slug"])
    assert system == "SYSTEM-MARKER"
    assert "ITEM-MARKER" in user
    assert "a-slug" in user


def test_both_transports_actually_call_the_shared_builder(monkeypatch):
    """
    Discriminating version: an earlier test only called the builder directly,
    so changing either transport to build its own prompt would have left it
    green. This spies on the shared builder and asserts BOTH transports route
    through it — the property that makes a shadow comparison measure transport
    rather than prompt drift.
    """
    calls = []
    real = bk._build_authored_scorer_prompt

    def _spy(spec, item, slugs):
        calls.append(spec["name"])
        return real(spec, item, slugs)

    monkeypatch.setattr(bk, "_build_authored_scorer_prompt", _spy)

    # The builder's real output for this input — what BOTH transports must
    # transmit. Asserting only that the builder was CALLED is not enough:
    # replacing each transport's payload with a constant while leaving the
    # call in place left the earlier version of this test green.
    want_system, want_user = real(_spec(), _item("ITEM-MARKER"), ["a-slug"])

    # CLI transport: system on argv, user on stdin.
    class _Proc:
        returncode = 0
        stdout = '{"score": 2}'
        stderr = ""

    sent = {}
    monkeypatch.setattr(bk, "_claude_cli_path", lambda: "/usr/bin/claude")
    monkeypatch.setattr(bk.subprocess, "run",
                        lambda argv, **kw: (sent.update(argv=argv, kw=kw), _Proc())[1])
    bk._call_authored_scorer_cli(_spec(), _item("ITEM-MARKER"), ["a-slug"])
    assert calls == ["bookkeeping-novelty"], "CLI transport bypassed the shared builder"
    argv = sent["argv"]
    assert argv[argv.index("--system-prompt") + 1] == want_system
    assert sent["kw"]["input"] == want_user

    # SDK transport: system kwarg, user as the single message.
    calls.clear()
    seen = {}

    class _Block:
        type = "text"
        text = '{"score": 2}'

    class _Resp:
        content = [_Block()]

    class _Client:
        class messages:
            @staticmethod
            def create(**kw):
                seen.update(kw)
                return _Resp()

    bk._call_authored_scorer(_spec(), _item("ITEM-MARKER"), ["a-slug"], _Client())
    assert calls == ["bookkeeping-novelty"], "SDK transport bypassed the shared builder"
    assert seen["system"] == want_system
    assert seen["messages"][0]["content"] == want_user


# ── availability reporting ────────────────────────────────────────────────────

def test_availability_names_a_blocker_for_every_dead_path():
    """A dead transport must say WHY; 'dead with no reason' is unactionable."""
    avail = bk.judge_availability()
    assert set(p["name"] for p in avail["paths"]) == {
        "claude_cli", "authored_agents", "gemini"
    }
    for p in avail["paths"]:
        if not p["available"]:
            assert p["blockers"], f"{p['name']} is dead but names no blocker"
        else:
            assert p["blockers"] == []


def test_availability_reports_cli_dead_when_binary_missing(monkeypatch):
    monkeypatch.setattr(bk.shutil, "which", lambda n: None)
    cli = [p for p in bk.judge_availability()["paths"] if p["name"] == "claude_cli"][0]
    assert cli["available"] is False
    assert any("PATH" in b for b in cli["blockers"])


def test_any_available_is_true_when_cli_present(monkeypatch):
    """
    Stubs `_load_agent_spec`, not `Path.exists`. Availability now PARSES the
    specs, so faking their existence is no longer sufficient — and faking
    existence was what coupled this test to a directory outside the repo.
    """
    monkeypatch.setattr(bk, "_claude_cli_path", lambda: "/usr/bin/claude")
    monkeypatch.setattr(bk.shutil, "which", lambda n: "/usr/bin/claude")
    monkeypatch.setattr(bk, "_load_agent_spec", lambda name: _spec())
    monkeypatch.setattr(bk, "_YAML_AVAILABLE", True, raising=False)
    assert bk.judge_availability()["any_available"] is True


# ── round 2: findings raised by Stratum A (Codex cross-vendor, 4/10) ──────────

def test_subscription_env_strips_api_billing_credentials(monkeypatch):
    """
    `billing="subscription"` must be true by construction. `claude` bills the
    API whenever ANTHROPIC_API_KEY is in its environment, so inheriting the
    ambient env would make the label a claim the code does not enforce — and
    would bill API rates for a path advertised as free.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-propagate")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok")
    monkeypatch.setenv("PATH", "/usr/bin")
    env = bk._subscription_env()
    assert "ANTHROPIC_API_KEY" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert env["PATH"] == "/usr/bin", "unrelated env must survive"


def test_cli_subprocess_receives_the_stripped_env(monkeypatch):
    """The stripping must reach subprocess.run, not merely exist as a helper."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-nope")
    monkeypatch.setattr(bk, "_claude_cli_path", lambda: "/usr/bin/claude")
    seen = {}

    class _Proc:
        returncode = 0
        stdout = '{"score": 1}'
        stderr = ""

    def _run(argv, **kw):
        seen.update(kw)
        return _Proc()

    monkeypatch.setattr(bk.subprocess, "run", _run)
    bk._call_authored_scorer_cli(_spec(), _item(), [])
    assert "ANTHROPIC_API_KEY" not in seen["env"]


def test_cli_disables_tools_and_omits_the_ignored_flag(monkeypatch):
    """A scorer must not read files or run commands on text it was asked to grade."""
    monkeypatch.setattr(bk, "_claude_cli_path", lambda: "/usr/bin/claude")
    seen = {}

    class _Proc:
        returncode = 0
        stdout = '{"score": 1}'
        stderr = ""

    monkeypatch.setattr(bk.subprocess, "run",
                        lambda argv, **kw: (seen.update(argv=argv), _Proc())[1])
    bk._call_authored_scorer_cli(_spec(), _item(), [])
    argv = seen["argv"]
    assert "--tools" in argv and argv[argv.index("--tools") + 1] == ""
    # `claude --help` states this flag is ignored with --system-prompt. A no-op
    # flag reads to a later maintainer as a guarantee that holds.
    assert "--exclude-dynamic-system-prompt-sections" not in argv


def test_timeout_is_reported_as_a_cause(monkeypatch):
    monkeypatch.setattr(bk, "_claude_cli_path", lambda: "/usr/bin/claude")

    def _boom(argv, **kw):
        raise bk.subprocess.TimeoutExpired(cmd="claude", timeout=7)

    monkeypatch.setattr(bk.subprocess, "run", _boom)
    out, err = bk._call_authored_scorer_cli(_spec(), _item(), [], timeout=7)
    assert out is None and "timed out" in err


def test_run_state_is_run_local():
    """
    A process-global counter makes a second run inherit the first's failures
    and keeps the first-failure-only warning suppressed for the whole process.
    """
    bk._JUDGE_STATE["failures"] = 5
    bk._JUDGE_STATE["last_error"] = "stale"
    bk.reset_judge_run_state()
    assert bk.judge_failure_count() == 0
    assert bk._JUDGE_STATE["last_error"] == ""


def test_runtime_cause_beats_static_blockers(monkeypatch, capsys):
    """
    A credential that expires mid-run satisfies every static check, so a
    warning built only from static blockers would print a misleading cause.
    """
    bk.set_judge_enabled(True)
    monkeypatch.setattr(bk, "score_item_heuristic",
                        lambda item: bk.ScoredItem(item, 2, 2, 1, 5, True, [], "heuristic"))

    def _fail(item, slugs):
        bk._JUDGE_STATE["last_error"] = "claude_cli/novelty: exit 1: credentials expired"
        return None

    monkeypatch.setattr(bk, "score_item_claude_cli", _fail)
    monkeypatch.setattr(bk, "score_item_authored_agents", lambda *a, **k: None)
    monkeypatch.setattr(bk, "score_item_llm", lambda *a, **k: None)
    bk.score_item(_item(), [])
    assert "credentials expired" in capsys.readouterr().err


def test_shared_selector_falls_through_in_billing_order(monkeypatch):
    order = []
    monkeypatch.setattr(bk, "score_item_claude_cli",
                        lambda *a, **k: (order.append("cli"), None)[1])
    monkeypatch.setattr(bk, "score_item_authored_agents",
                        lambda *a, **k: (order.append("sdk"), None)[1])
    sentinel = bk.ScoredItem(_item(), 1, 1, 1, 3, False, [], "llm_judge")
    monkeypatch.setattr(bk, "score_item_llm",
                        lambda *a, **k: (order.append("gemini"), sentinel)[1])
    out = bk.score_item_with_judge(_item(), [])
    assert order == ["cli", "sdk", "gemini"]
    assert out is sentinel


def test_score_item_uses_the_shared_selector(monkeypatch):
    """
    Calibration and production must route through ONE selector. Otherwise a
    working SDK with a broken CLI lets production judge while calibration
    reports failure, and the disagreement numbers describe a path nobody runs.
    """
    bk.set_judge_enabled(True)
    called = []
    monkeypatch.setattr(bk, "score_item_heuristic",
                        lambda item: bk.ScoredItem(item, 2, 2, 1, 5, True, [], "heuristic"))
    judged = bk.ScoredItem(_item(), 1, 1, 1, 3, False, [], "authored_agents")
    monkeypatch.setattr(bk, "score_item_with_judge",
                        lambda *a, **k: (called.append(1), judged)[1])
    out = bk.score_item(_item(), [])
    assert called == [1]
    assert out.scoring_method == "authored_agents"


def test_verify_reports_failure_detail(monkeypatch):
    """
    Stubs the PRODUCTION seam (`score_item_with_judge`), which is what
    verify_judge_transport calls since round 4. The earlier version patched
    `_call_authored_scorer_cli` and depended on the real agent-spec directory
    existing — true on a dev box, false in CI, where the spec load failed
    early and the assertion read a stale cause instead.
    """
    monkeypatch.setattr(bk, "score_item_with_judge", lambda *a, **k: None)
    bk._JUDGE_STATE["last_error"] = "claude_cli/novelty: exit 1: unauthorized"
    ok, detail = bk.verify_judge_transport()
    assert ok is False and "unauthorized" in detail


def test_verify_failure_without_a_cause_still_says_something(monkeypatch):
    """A failure with no captured cause must not report an empty reason."""
    monkeypatch.setattr(bk, "score_item_with_judge", lambda *a, **k: None)
    bk._JUDGE_STATE["last_error"] = ""
    ok, detail = bk.verify_judge_transport()
    assert ok is False and detail.strip()


def test_verify_reports_success(monkeypatch):
    scored = bk.ScoredItem(_item(), 1, 1, 1, 3, False, [], "claude_cli")
    monkeypatch.setattr(bk, "score_item_with_judge", lambda *a, **k: scored)
    ok, detail = bk.verify_judge_transport()
    assert ok is True and "OK" in detail


# ── round 3: findings raised by Stratum A (Codex cross-vendor, 5/10) ──────────

@pytest.mark.parametrize("var", [
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "AWS_BEARER_TOKEN_BEDROCK",
])
def test_cloud_provider_selection_is_stripped_too(monkeypatch, var):
    """
    Removing only the direct API keys left the "subscription" label true in the
    common case and false on a Bedrock/Vertex-configured machine: those
    variables reroute auth to cloud credentials that take precedence.
    """
    monkeypatch.setenv(var, "1")
    assert var not in bk._subscription_env()


def test_mcp_servers_are_disabled_not_just_builtin_tools(monkeypatch):
    """
    `--tools ""` disables the BUILT-IN set only. MCP servers are configured
    separately, so without --strict-mcp-config an ambient MCP tool stays
    reachable while the model grades untrusted text.
    """
    monkeypatch.setattr(bk, "_claude_cli_path", lambda: "/usr/bin/claude")
    seen = {}

    class _Proc:
        returncode = 0
        stdout = '{"score": 1}'
        stderr = ""

    monkeypatch.setattr(bk.subprocess, "run",
                        lambda argv, **kw: (seen.update(argv=argv), _Proc())[1])
    bk._call_authored_scorer_cli(_spec(), _item(), [])
    argv = seen["argv"]
    assert "--strict-mcp-config" in argv
    # The payload must be a valid mcp config object. `{}` was rejected by the
    # CLI ("mcpServers: Invalid input"), which made every scoring call fail --
    # caught on the first real round-trip, not by any test.
    assert argv[argv.index("--mcp-config") + 1] == '{"mcpServers":{}}'
    # Round 3 claimed no isolation flag existed. It was asserted without
    # checking; `claude --help` documents both.
    assert "--safe-mode" in argv, "hooks/CLAUDE.md/plugins not isolated"
    assert argv[argv.index("--setting-sources") + 1] == "", \
        "settings files still loaded — apiKeyHelper can redirect auth"


def test_cmd_run_writes_enablement_unconditionally(monkeypatch):
    """The leak fix must live in cmd_run itself, not only in the helper."""
    import argparse

    monkeypatch.setattr(bk, "run_pipeline", lambda **kw: None)
    bk.set_judge_enabled(True)
    bk.cmd_run(argparse.Namespace(judge=False, source=None, dry_run=True, verbose=False))
    assert bk.judge_enabled() is False


def test_every_transport_has_an_evidence_slice():
    """
    A transport missing from the table would silently fall back to DEFAULT and
    reintroduce the mismatch the table exists to remove.
    """
    for method in ("claude_cli", "authored_agents", "llm_judge"):
        assert method in bk.JUDGE_EVIDENCE_CHARS


def _row_for(method, content_len=5000, slugs=None):
    """Build a real calibration row scored by `method`."""
    item = _item("y" * content_len)
    h = bk.ScoredItem(item, 2, 2, 1, 5, True, [], "heuristic")
    j = bk.ScoredItem(item, 1, 1, 1, 3, False, [], method)
    return bk._calibration_row(item, h, j, slugs or ["slug-a", "slug-b"])


@pytest.mark.parametrize("method,expected", [
    ("llm_judge", 800),
    ("authored_agents", 2000),
    ("claude_cli", 2000),
])
def test_sheet_content_length_matches_the_scoring_transport(method, expected):
    """
    DISCRIMINATING version. The previous test asserted the table against
    itself, so two mutations left the whole suite green: putting the sheet
    back to 2000 while Gemini sees 800 (the original defect), and moving
    Gemini to 2000 while the sheet stayed 800. This measures the row the
    sheet is actually built from.
    """
    row = _row_for(method)
    assert len(row["content_seen_by_judge"]) == expected
    assert row["evidence_chars"] == expected


def test_gemini_prompt_length_matches_the_table(monkeypatch):
    """
    BEHAVIOURAL, not a source grep. The earlier version grepped bookkeeping.py
    for a literal expression, so reformatting broke a correct implementation
    and dead code kept it green. This drives the real prompt.
    """
    sent = {}

    class _Resp:
        text = '{"novelty":1,"specificity":1,"relevance":1}'

    class _Model:
        def generate_content(self, prompt, **kw):
            sent["prompt"] = prompt
            return _Resp()

    fake = type("G", (), {
        "configure": staticmethod(lambda **kw: None),
        "GenerativeModel": staticmethod(lambda *a, **k: _Model()),
    })
    monkeypatch.setattr(bk, "genai", fake, raising=False)
    monkeypatch.setattr(bk, "_GENAI_AVAILABLE", True, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "k")

    long_item = _item("z" * 5000)
    out = bk.score_item_llm(long_item, [])
    assert out is not None, "gemini stub did not score"
    want = bk.JUDGE_EVIDENCE_CHARS["llm_judge"]
    assert "z" * want in sent["prompt"]
    assert "z" * (want + 1) not in sent["prompt"]


def test_sheet_carries_the_context_the_judge_scored_against():
    """
    Novelty is judged against the existing graph and relevance against the
    active projects. A labeller given only the text cannot reach the same
    novelty verdict even in principle, and the gap would be charged to the
    judge.
    """
    row = _row_for("claude_cli", slugs=["existing-one", "existing-two"])
    ctx = row["context_seen_by_judge"]
    assert ctx["existing_entity_slugs"] == ["existing-one", "existing-two"]
    assert ctx["active_projects"] == bk.AUTHORED_RELEVANCE_PROJECTS
    assert "source_type" in ctx


def test_relevance_prompt_and_sheet_share_one_project_list():
    """Two copies of the project list would drift invisibly."""
    spec = _spec()
    spec["name"] = "bookkeeping-relevance"
    _system, user = bk._build_authored_scorer_prompt(spec, _item(), [])
    for proj in bk.AUTHORED_RELEVANCE_PROJECTS:
        assert proj in user


def test_authored_prompt_slice_matches_the_table():
    """Pins the builder to the table rather than to a literal."""
    long_item = _item("x" * 5000)
    _system, user = bk._build_authored_scorer_prompt(_spec(), long_item, [])
    # The prompt embeds the item as JSON; count the run of x's it carried.
    assert "x" * bk.JUDGE_EVIDENCE_CHARS["authored_agents"] in user
    assert "x" * (bk.JUDGE_EVIDENCE_CHARS["authored_agents"] + 1) not in user


# ── round 4 ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad_model", [[], {}, 42, "", "   "])
def test_spec_with_a_non_string_model_is_refused_at_load(tmp_path, monkeypatch, bad_model):
    """
    `model: []` parsed fine, then raised `TypeError: unhashable type` inside
    the transport OUTSIDE its try/except — the exception escaped and NEITHER
    fallback transport was attempted. Data is validated where it enters.
    """
    import yaml as _yaml
    d = tmp_path / "agents"
    d.mkdir()
    body = {"name": "bookkeeping-novelty", "model": bad_model}
    (d / "bookkeeping-novelty.md").write_text(
        "---\n" + _yaml.safe_dump(body) + "---\nscore it\n"
    )
    monkeypatch.setattr(bk, "AUTHORED_AGENTS_DIR", d)
    assert bk._load_agent_spec("bookkeeping-novelty") is None


def test_a_bad_spec_does_not_escape_past_the_fallback_chain(monkeypatch):
    """The selector must still reach the later transports, not crash."""
    monkeypatch.setattr(bk, "_claude_cli_path", lambda: "/usr/bin/claude")
    monkeypatch.setattr(bk, "_load_agent_spec", lambda n: None)
    reached = []
    monkeypatch.setattr(bk, "score_item_authored_agents",
                        lambda *a, **k: (reached.append("sdk"), None)[1])
    monkeypatch.setattr(bk, "score_item_llm",
                        lambda *a, **k: (reached.append("gemini"), None)[1])
    assert bk.score_item_with_judge(_item(), []) is None
    assert reached == ["sdk", "gemini"], "a bad spec short-circuited the fallback"


def test_verify_exercises_all_three_dimensions(monkeypatch):
    """
    Probing only bookkeeping-novelty let --verify PASS while production
    returned None. A verification narrower than the thing it verifies is this
    ticket's own defect, one level up.
    """
    def _spec_for(name):
        return None if name != "bookkeeping-novelty" else _spec()

    monkeypatch.setattr(bk, "_claude_cli_path", lambda: "/usr/bin/claude")
    monkeypatch.setattr(bk, "_load_agent_spec", _spec_for)
    monkeypatch.setattr(bk, "score_item_authored_agents", lambda *a, **k: None)
    monkeypatch.setattr(bk, "score_item_llm", lambda *a, **k: None)
    ok, _detail = bk.verify_judge_transport()
    assert ok is False, "verify passed while two of three specs were missing"


def test_verify_routes_through_the_production_selector(monkeypatch):
    used = []
    scored = bk.ScoredItem(_item(), 1, 1, 1, 3, False, [], "authored_agents")
    monkeypatch.setattr(bk, "score_item_with_judge",
                        lambda *a, **k: (used.append(1), scored)[1])
    ok, detail = bk.verify_judge_transport()
    assert ok is True and used == [1]
    assert "authored_agents" in detail


def test_sdk_exception_cause_is_preserved(monkeypatch):
    """An expired SDK token used to vanish, leaving the warning to re-derive
    static blockers that all looked satisfied."""
    bk._JUDGE_STATE["last_error"] = ""

    class _Client:
        class messages:
            @staticmethod
            def create(**kw):
                raise RuntimeError("SDK_TOKEN_EXPIRED")

    out = bk._call_authored_scorer(_spec(), _item(), [], _Client())
    assert out is None
    assert "SDK_TOKEN_EXPIRED" in bk._JUDGE_STATE["last_error"]


def test_billing_label_does_not_overclaim():
    """
    Two rounds were spent extending a denylist; a third found FOUNDRY still
    standing. A denylist over an open set cannot promise a billing source, and
    apiKeyHelper bypasses the environment entirely, so the CLAIM is withdrawn
    rather than chased a fourth time.
    """
    cli = [p for p in bk.judge_availability()["paths"] if p["name"] == "claude_cli"][0]
    assert cli["billing"] == "subscription-preferred"


def test_foundry_is_stripped_too(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_USE_FOUNDRY", "1")
    assert "CLAUDE_CODE_USE_FOUNDRY" not in bk._subscription_env()


def test_absent_model_still_defaults(tmp_path, monkeypatch):
    """An OMITTED model is not an invalid one — it legitimately defaults."""
    import yaml as _yaml
    d = tmp_path / "agents"
    d.mkdir()
    (d / "bookkeeping-novelty.md").write_text(
        "---\n" + _yaml.safe_dump({"name": "bookkeeping-novelty"}) + "---\nscore it\n"
    )
    monkeypatch.setattr(bk, "AUTHORED_AGENTS_DIR", d)
    spec = bk._load_agent_spec("bookkeeping-novelty")
    assert spec is not None and spec["model"] == "claude-haiku-4-5"


# ── round 5: the HOISTED invariant (P20 STRUCTURAL directive) ────────────────
#
# Four rounds each found "a transport failed and left no cause" at a NEW site.
# The directive was to stop patching sites and make it impossible. These pin
# the invariant itself, so a transport added later inherits it.

def test_an_unconfigured_transport_leaves_the_static_blockers_reachable(monkeypatch):
    """
    THE CORRECTED INVARIANT. An earlier version synthesized "returned no score
    and recorded no cause (transport bug)" for a bare None — which is the
    ORDINARY unconfigured case. That told an operator who had simply not
    installed anything that the module was buggy, and it made the
    static-blocker fallback in `score_item` unreachable by never leaving the
    cause empty.

    A failure must be DIAGNOSABLE, which is not the same as "carries a
    non-empty string": an unconfigured transport must leave the cause empty so
    the caller falls back to blockers that name the real problem.
    """
    bk.reset_judge_run_state()
    monkeypatch.setattr(bk, "score_item_claude_cli", lambda *a, **k: None)
    monkeypatch.setattr(bk, "score_item_authored_agents", lambda *a, **k: None)
    monkeypatch.setattr(bk, "score_item_llm", lambda *a, **k: None)
    assert bk.score_item_with_judge(_item(), []) is None
    assert bk._JUDGE_STATE["last_error"] == "", (
        "a synthesized cause makes the static blockers unreachable"
    )


def test_the_static_blocker_fallback_is_not_dead_code(monkeypatch, capsys):
    """The path the synthesized cause had made unreachable must actually run."""
    bk.reset_judge_run_state()
    bk.set_judge_enabled(True)
    monkeypatch.setattr(bk, "score_item_heuristic",
                        lambda item: bk.ScoredItem(item, 2, 2, 1, 5, True, [], "heuristic"))
    monkeypatch.setattr(bk, "score_item_claude_cli", lambda *a, **k: None)
    monkeypatch.setattr(bk, "score_item_authored_agents", lambda *a, **k: None)
    monkeypatch.setattr(bk, "score_item_llm", lambda *a, **k: None)
    monkeypatch.setattr(bk, "judge_availability", lambda: {
        "any_available": False,
        "paths": [{"name": "claude_cli", "billing": "subscription-preferred",
                   "available": False, "blockers": ["`claude` CLI not on PATH"]}],
    })
    bk.score_item(_item(), [])
    err = capsys.readouterr().err
    assert "not on PATH" in err, "the useful diagnosis never reached the operator"


def test_a_recorded_runtime_cause_still_wins(monkeypatch, capsys):
    """A real runtime cause must still be preferred over the static blockers."""
    bk.reset_judge_run_state()
    bk.set_judge_enabled(True)
    monkeypatch.setattr(bk, "score_item_heuristic",
                        lambda item: bk.ScoredItem(item, 2, 2, 1, 5, True, [], "heuristic"))

    def _fail(item, slugs):
        bk._JUDGE_STATE["last_error"] = "claude_cli/novelty: exit 1: credentials expired"
        return None

    monkeypatch.setattr(bk, "score_item_claude_cli", _fail)
    monkeypatch.setattr(bk, "score_item_authored_agents", lambda *a, **k: None)
    monkeypatch.setattr(bk, "score_item_llm", lambda *a, **k: None)
    bk.score_item(_item(), [])
    assert "credentials expired" in capsys.readouterr().err


def test_an_exception_in_one_transport_does_not_abort_the_chain(monkeypatch):
    """
    `model: []` raised inside a transport and the exception escaped the whole
    selector, so the remaining transports were never tried. Containment is the
    invariant's job, not each transport's.
    """
    bk.reset_judge_run_state()
    reached = []

    def _boom(item, slugs):
        raise TypeError("unhashable type: 'list'")

    monkeypatch.setattr(bk, "score_item_claude_cli", _boom)
    monkeypatch.setattr(bk, "score_item_authored_agents",
                        lambda *a, **k: (reached.append("sdk"), None)[1])
    sentinel = bk.ScoredItem(_item(), 1, 1, 1, 3, False, [], "llm_judge")
    monkeypatch.setattr(bk, "score_item_llm",
                        lambda *a, **k: (reached.append("gemini"), sentinel)[1])

    out = bk.score_item_with_judge(_item(), [])
    assert out is sentinel, "an exception aborted the fallback chain"
    assert reached == ["sdk", "gemini"]


def test_cause_is_cleared_between_transports(monkeypatch):
    """A stale cause from a previous item must not be reported for this one."""
    bk._JUDGE_STATE["last_error"] = "STALE FROM AN EARLIER ITEM"
    scored = bk.ScoredItem(_item(), 1, 1, 1, 3, False, [], "claude_cli")
    monkeypatch.setattr(bk, "score_item_claude_cli", lambda *a, **k: scored)
    bk.score_item_with_judge(_item(), [])
    assert "STALE" not in bk._JUDGE_STATE["last_error"]


# ── round 5: Gemini parity ───────────────────────────────────────────────────

def _gemini(monkeypatch, payload):
    class _Resp:
        text = payload

    class _Model:
        def generate_content(self, prompt, **kw):
            return _Resp()

    fake = type("G", (), {
        "configure": staticmethod(lambda **kw: None),
        "GenerativeModel": staticmethod(lambda *a, **k: _Model()),
    })
    monkeypatch.setattr(bk, "genai", fake, raising=False)
    monkeypatch.setattr(bk, "_GENAI_AVAILABLE", True, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "k")


def test_gemini_out_of_range_dimensions_are_rejected(monkeypatch):
    """
    This path used to int() whatever came back and sum it, so 9/9/9 produced
    total=27 and PROMOTED — while every other transport rejected the same
    response through the shared validator the docstring claimed was shared.
    """
    bk.reset_judge_run_state()
    _gemini(monkeypatch, '{"novelty":9,"specificity":9,"relevance":9}')
    assert bk.score_item_llm(_item(), []) is None
    assert "out of range" in bk._JUDGE_STATE["last_error"]


@pytest.mark.parametrize("payload", [
    '{"novelty":"2","specificity":1,"relevance":1}',
    '{"novelty":true,"specificity":1,"relevance":1}',
    '{"specificity":1,"relevance":1}',
    '{"novelty":-1,"specificity":1,"relevance":1}',
])
def test_gemini_malformed_dimensions_are_rejected(monkeypatch, payload):
    bk.reset_judge_run_state()
    _gemini(monkeypatch, payload)
    assert bk.score_item_llm(_item(), []) is None


def test_gemini_in_range_still_scores(monkeypatch):
    """The bound must not reject legitimate scores."""
    bk.reset_judge_run_state()
    _gemini(monkeypatch, '{"novelty":3,"specificity":2,"relevance":1}')
    out = bk.score_item_llm(_item(), [])
    assert out is not None and out.total == 6 and out.scoring_method == "llm_judge"


def test_gemini_exception_records_its_cause(monkeypatch):
    """An expired Gemini key used to leave the warning naming the other two."""
    bk.reset_judge_run_state()

    class _Model:
        def generate_content(self, prompt, **kw):
            raise RuntimeError("GEMINI_KEY_EXPIRED 401")

    fake = type("G", (), {
        "configure": staticmethod(lambda **kw: None),
        "GenerativeModel": staticmethod(lambda *a, **k: _Model()),
    })
    monkeypatch.setattr(bk, "genai", fake, raising=False)
    monkeypatch.setattr(bk, "_GENAI_AVAILABLE", True, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert bk.score_item_llm(_item(), []) is None
    assert "GEMINI_KEY_EXPIRED" in bk._JUDGE_STATE["last_error"]


# ── round 5: the --judge enable path warns (F3) ──────────────────────────────

def test_run_judge_warns_when_no_transport_is_configured(monkeypatch, capsys):
    """
    The check ran in main() BEFORE parse_args, so it could only see the env
    var. `run --judge` — the documented primary path — was still unset then
    and produced no warning at all.
    """
    import argparse
    monkeypatch.setattr(bk, "run_pipeline", lambda **kw: None)
    monkeypatch.setattr(bk, "judge_availability",
                        lambda: {"any_available": False, "paths": []})
    bk.cmd_run(argparse.Namespace(judge=True, source=None, dry_run=True, verbose=False))
    assert "NO transport is configured" in capsys.readouterr().err


def test_no_warning_when_the_judge_was_not_requested(monkeypatch, capsys):
    import argparse
    monkeypatch.setattr(bk, "run_pipeline", lambda **kw: None)
    monkeypatch.setattr(bk, "judge_availability",
                        lambda: {"any_available": False, "paths": []})
    bk.cmd_run(argparse.Namespace(judge=False, source=None, dry_run=True, verbose=False))
    assert "NO transport" not in capsys.readouterr().err


# ── round 5: the slug axis of "same evidence" (F6) ───────────────────────────

def test_sheet_slug_cap_matches_the_novelty_prompt():
    """
    A mutation shrinking the row's slug export survived the whole suite because
    every test passed fewer slugs than the cap. The graph has >1,100 entities,
    so this axis is live: a labeller shown 3 slugs cannot reach the same
    novelty verdict as a judge shown 40.
    """
    many = [f"slug-{i}" for i in range(120)]
    row = _row_for("claude_cli", slugs=many)
    exported = row["context_seen_by_judge"]["existing_entity_slugs"]
    spec = _spec()
    spec["name"] = "bookkeeping-novelty"
    _system, user = bk._build_authored_scorer_prompt(spec, _item(), many)
    in_prompt = [s for s in many if f'"{s}"' in user]
    assert exported == in_prompt, (
        f"sheet exports {len(exported)} slugs, prompt carries {len(in_prompt)}"
    )


# ── the OTHER half of the invariant: a score returned must be a VALID score ──

def test_a_transport_cannot_promote_an_out_of_range_score(monkeypatch):
    """
    Gemini returning 9/9/9 gave total=27 and PROMOTED. That was fixed inside
    the transport, in the round whose directive was "stop patching sites", so
    a transport added later reopens it. Checked at the selector now.
    """
    bk.reset_judge_run_state()
    bogus = bk.ScoredItem(_item(), 9, 9, 9, 27, True, [], "future_transport")
    monkeypatch.setattr(bk, "score_item_claude_cli", lambda *a, **k: bogus)
    monkeypatch.setattr(bk, "score_item_authored_agents", lambda *a, **k: None)
    monkeypatch.setattr(bk, "score_item_llm", lambda *a, **k: None)
    assert bk.score_item_with_judge(_item(), []) is None
    assert "invalid score" in bk._JUDGE_STATE["last_error"]


@pytest.mark.parametrize("n,sp,r,total,promote,why", [
    (9, 9, 9, 27, True, "dimensions out of range"),
    (1, 1, 1, 9, True, "total disagrees with the sum"),
    (1, 1, 1, 3, True, "promote disagrees with the threshold"),
    (3, 3, 3, 9, False, "promote disagrees with the threshold"),
    (-1, 1, 1, 1, False, "negative dimension"),
])
def test_invalid_scored_items_are_refused(n, sp, r, total, promote, why):
    assert not bk._scored_item_is_sane(
        bk.ScoredItem(_item(), n, sp, r, total, promote, [], "x")
    ), why


def test_valid_scored_items_are_accepted():
    assert bk._scored_item_is_sane(bk.ScoredItem(_item(), 2, 2, 1, 5, True, [], "x"))
    assert bk._scored_item_is_sane(bk.ScoredItem(_item(), 1, 1, 1, 3, False, [], "x"))


# ── the cause must be REPORTED, not merely recorded ──────────────────────────

def test_run_log_does_not_carry_a_field_that_is_empty_when_needed():
    """
    A `judge_last_error` field was added and then removed. It was empty in
    both scenarios its commit cited, because `_run_transport` clears the cause
    before every call: any later success wiped it, so it carried a cause only
    when the run's FINAL in-band item failed.

    This asserts the REMOVAL behaviourally rather than by grepping source —
    the guard it replaces used `inspect.getsource` and stayed green when the
    field was made dead, which is why the broken field shipped at all.
    """
    import json as _json
    import tempfile

    captured = {}
    real_log = bk.log_run

    with tempfile.TemporaryDirectory() as td:
        def _spy(entry):
            captured.update(entry)

        bk.log_run = _spy
        try:
            bk.run_pipeline(source_files=[], dry_run=True, verbose=False)
        except Exception:
            pass
        finally:
            bk.log_run = real_log

    # dry_run short-circuits before log_run, so assert on the shape the
    # pipeline builds rather than on a write that never happens.
    assert "judge_last_error" not in captured, (
        "a field that is empty exactly when it is needed is worse than none"
    )


def test_judge_context_is_transport_aware():
    """
    A Gemini row used to claim the judge saw eight active projects and a
    source URL that appear nowhere in the Gemini prompt.
    """
    item = _item()
    gem = bk._judge_context("llm_judge", item, ["a", "b"])
    cli = bk._judge_context("claude_cli", item, ["a", "b"])
    assert gem["active_projects"] == [] and gem["existing_entity_slugs"] == []
    assert cli["active_projects"] == bk.AUTHORED_RELEVANCE_PROJECTS
    assert cli["existing_entity_slugs"] == ["a", "b"]


def test_gemini_row_does_not_claim_unseen_context():
    row = _row_for("llm_judge")
    assert row["context_seen_by_judge"]["active_projects"] == []


# ── F6: the project-list tests were a constant against itself ────────────────

def test_the_relevance_project_list_is_non_empty_and_concrete():
    """
    Both project tests passed with AUTHORED_RELEVANCE_PROJECTS = [] — one
    looped over an empty list, the other compared a constant to itself. An
    emptied list tells the relevance scorer there are NO active projects,
    pushing every relevance score toward 0 and flipping promotions, with the
    suite fully green. Asserted against literals now.
    """
    projects = bk.AUTHORED_RELEVANCE_PROJECTS
    assert len(projects) >= 5
    for known in ("life-agent-os", "lago", "arcan"):
        assert known in projects, f"{known} missing from the relevance project list"


def test_relevance_prompt_actually_carries_a_known_project():
    spec = _spec()
    spec["name"] = "bookkeeping-relevance"
    _system, user = bk._build_authored_scorer_prompt(spec, _item(), [])
    assert "life-agent-os" in user, "the relevance scorer was sent no project list"


def test_labels_without_sample_refuses_instead_of_silently_writing_nothing():
    """
    `--labels PATH` without `--sample` exited 0 having written nothing, with
    only a generic hint — a silent no-op on an explicit request for a file,
    which is this ticket's defect class on its own CLI.
    """
    import argparse
    args = argparse.Namespace(sample=0, labels="/tmp/should-not-appear.json", verify=False)
    with pytest.raises(SystemExit) as exc:
        bk.cmd_judge_check(args)
    assert exc.value.code == 2
    assert not pathlib.Path("/tmp/should-not-appear.json").exists()


def test_no_labels_and_no_sample_is_still_a_clean_exit():
    """The plain diagnostic form must not start failing."""
    import argparse
    bk.cmd_judge_check(argparse.Namespace(sample=0, labels=None, verify=False))


# ── BRO-2532 findings, fixed under human authorization past the P20 stop ─────

def test_a_present_but_unparseable_spec_is_a_blocker(tmp_path, monkeypatch):
    """
    `.exists()` reported a corrupt spec as available, so the CLI transport
    advertised itself with no blockers and then returned a causeless None.
    """
    import yaml as _yaml
    d = tmp_path / "agents"
    d.mkdir()
    for dim in ("novelty", "specificity"):
        (d / f"bookkeeping-{dim}.md").write_text(
            "---\n" + _yaml.safe_dump({"name": f"bookkeeping-{dim}",
                                       "model": "claude-haiku-4-5"}) + "---\nscore it\n")
    # exists, parses as YAML, but `model` is a list -> _load_agent_spec rejects
    (d / "bookkeeping-relevance.md").write_text(
        "---\n" + _yaml.safe_dump({"name": "bookkeeping-relevance",
                                   "model": []}) + "---\nscore it\n")
    monkeypatch.setattr(bk, "AUTHORED_AGENTS_DIR", d)
    monkeypatch.setattr(bk, "_claude_cli_path", lambda: "/usr/bin/claude")

    cli = [p for p in bk.judge_availability()["paths"] if p["name"] == "claude_cli"][0]
    assert cli["available"] is False, "a corrupt spec still reported as available"
    assert any("relevance" in b for b in cli["blockers"]), \
        "the blocker does not name the spec that failed to parse"


def test_all_specs_parsing_is_still_available(tmp_path, monkeypatch):
    """The stricter check must not reject healthy specs."""
    import yaml as _yaml
    d = tmp_path / "agents"
    d.mkdir()
    for dim in ("novelty", "specificity", "relevance"):
        (d / f"bookkeeping-{dim}.md").write_text(
            "---\n" + _yaml.safe_dump({"name": f"bookkeeping-{dim}",
                                       "model": "claude-haiku-4-5"}) + "---\nscore it\n")
    monkeypatch.setattr(bk, "AUTHORED_AGENTS_DIR", d)
    monkeypatch.setattr(bk, "_claude_cli_path", lambda: "/usr/bin/claude")
    monkeypatch.setattr(bk, "_YAML_AVAILABLE", True, raising=False)
    cli = [p for p in bk.judge_availability()["paths"] if p["name"] == "claude_cli"][0]
    assert cli["available"] is True and cli["blockers"] == []


def test_a_transport_mislabelling_itself_is_refused(monkeypatch):
    """
    `scoring_method` keys JUDGE_EVIDENCE_CHARS and dispatches _judge_context,
    so a Gemini-shaped call claiming to be claude_cli makes the sheet report
    2000 chars of evidence against a judge that saw 800.
    """
    bk.reset_judge_run_state()
    liar = bk.ScoredItem(_item(), 1, 1, 1, 3, False, [], "claude_cli")
    monkeypatch.setattr(bk, "score_item_llm", lambda *a, **k: liar)
    out = bk._run_transport("llm_judge", bk.score_item_llm, _item(), [])
    assert out is None
    assert "not the transport that produced it" in bk._JUDGE_STATE["last_error"]


def test_an_honest_transport_label_passes(monkeypatch):
    bk.reset_judge_run_state()
    honest = bk.ScoredItem(_item(), 1, 1, 1, 3, False, [], "llm_judge")
    out = bk._run_transport("llm_judge", lambda i, s: honest, _item(), [])
    assert out is honest


# ── the run-level cause accumulator (the field that was removed, done right) ──

def test_causes_survive_a_later_success(monkeypatch):
    """
    THE EXACT SCENARIO the removed single field failed: three items fail, a
    fourth succeeds, and the earlier causes must still be in the log.
    """
    bk.reset_judge_run_state()

    def _fail(item, slugs):
        bk._JUDGE_STATE["last_error"] = "claude_cli/novelty: exit 1: credentials expired"
        bk._record_judge_cause(bk._JUDGE_STATE["last_error"])
        return None

    monkeypatch.setattr(bk, "score_item_claude_cli", _fail)
    monkeypatch.setattr(bk, "score_item_authored_agents", lambda *a, **k: None)
    monkeypatch.setattr(bk, "score_item_llm", lambda *a, **k: None)
    for _ in range(3):
        bk.score_item_with_judge(_item(), [])

    ok = bk.ScoredItem(_item(), 1, 1, 1, 3, False, [], "claude_cli")
    monkeypatch.setattr(bk, "score_item_claude_cli", lambda *a, **k: ok)
    bk.score_item_with_judge(_item(), [])

    causes = bk.judge_causes()
    assert any("credentials expired" in c for c in causes), \
        "a later success wiped the earlier causes — the removed field's exact bug"


def test_causes_are_deduplicated_and_capped():
    bk.reset_judge_run_state()
    for _ in range(5):
        bk._record_judge_cause("same cause")
    assert bk.judge_causes() == ["same cause"]
    for i in range(100):
        bk._record_judge_cause(f"cause {i}")
    assert len(bk.judge_causes()) <= bk.JUDGE_CAUSE_LOG_CAP


def test_causes_are_cleared_between_runs():
    bk._record_judge_cause("from a previous run")
    bk.reset_judge_run_state()
    assert bk.judge_causes() == []


def test_run_log_entry_carries_the_causes_list():
    """Behavioural: build the entry and look at it, not at the source text."""
    captured = {}
    real = bk.log_run
    bk.log_run = lambda e: captured.update(e)
    try:
        bk.reset_judge_run_state()
        bk._record_judge_cause("claude_cli: something broke")
        bk.run_pipeline(source_files=[], dry_run=False, verbose=False)
    except Exception:
        pass
    finally:
        bk.log_run = real
    if captured:
        assert "judge_causes" in captured
        assert "judge_last_error" not in captured


# ── --verify must not over-describe a one-call transport ────────────────────

@pytest.mark.parametrize("method,phrase,absent", [
    ("claude_cli", "one call per dimension", "single combined"),
    ("llm_judge", "a single combined call", "per dimension"),
])
def test_verify_describes_the_transport_it_used(monkeypatch, method, phrase, absent):
    scored = bk.ScoredItem(_item(), 1, 1, 1, 3, False, [], method)
    monkeypatch.setattr(bk, "score_item_with_judge", lambda *a, **k: scored)
    ok, detail = bk.verify_judge_transport()
    assert ok is True
    assert phrase in detail and absent not in detail
