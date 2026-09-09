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
    bk._JUDGE_STATE["failures"] = 0
    yield
    bk.set_judge_enabled(False)
    bk._JUDGE_STATE["failures"] = 0


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
        return None if calls["n"] == 2 else {"score": 2, "reasoning": "ok"}

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
    out = bk._call_authored_scorer_cli(spec, _item("rm -rf / ; $(whoami) `id`"), [])

    assert out == {"score": 2}
    assert seen["kw"].get("shell") is False
    assert isinstance(seen["argv"], list)
    # The untrusted item text goes on stdin, not argv.
    assert "rm -rf" not in " ".join(seen["argv"])
    assert "rm -rf" in seen["kw"]["input"]


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
    assert bk._call_authored_scorer_cli(spec, _item(), []) is None


# ── prompt fidelity across transports ─────────────────────────────────────────

def test_both_transports_share_one_prompt_builder():
    """
    If each transport built its own prompt, a shadow comparison between them
    would measure prompt drift rather than transport, and the calibration
    numbers would be quietly meaningless.
    """
    spec = {"name": "bookkeeping-novelty", "model": "claude-haiku-4-5",
            "max_turns": 1, "input_schema": {}, "output_schema": {"score": "int"},
            "instructions": "SYSTEM-MARKER"}
    system, user = bk._build_authored_scorer_prompt(spec, _item("ITEM-MARKER"), ["a-slug"])
    assert system == "SYSTEM-MARKER"
    assert "ITEM-MARKER" in user
    assert "a-slug" in user


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
    monkeypatch.setattr(bk, "_claude_cli_path", lambda: "/usr/bin/claude")
    monkeypatch.setattr(bk.shutil, "which", lambda n: "/usr/bin/claude")
    monkeypatch.setattr(bk.Path, "exists", lambda self: True)
    assert bk.judge_availability()["any_available"] is True
