"""Tests for the session-scoped talkback turn-end hook.

The property under test is **isolation**, and isolation is only demonstrated by
a pair: a session that opted in must speak, and a *concurrent* session that did
not must stay silent under the identical setup. A one-sided test passes just as
happily against a hook that never speaks at all, which is the failure mode this
whole change exists to prevent.

Nothing here synthesises audio. `speak_detached` is the seam: every behavioural
test asserts on whether it was called and with what.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import shlex
import sys
import time
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "talkback-hook.py"

SESSION_A = "aaaaaaaa-0000-4000-8000-000000000001"
SESSION_B = "bbbbbbbb-0000-4000-8000-000000000002"

LONG_TURN = (
    "Rewrote the resolver so the flag is keyed on the session id instead of one "
    "global file, then wired the SessionEnd cleanup and the idle janitor behind it."
)


def _load_with_env():
    """Re-import so env-read module constants (CAP, FULL_MAX_CHARS) take."""
    return _load()


def _load():
    spec = importlib.util.spec_from_file_location("talkback_hook_under_test", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["talkback_hook_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def hook(tmp_path, monkeypatch):
    """The module, with all state redirected into a tmp dir."""
    monkeypatch.setenv("TALKBACK_HOME", str(tmp_path / "talkback"))
    monkeypatch.delenv("TALKBACK_HOOK_MODE", raising=False)
    monkeypatch.delenv("TALKBACK_HOOK_BACKEND", raising=False)
    monkeypatch.delenv("TALKBACK_OUTPUT", raising=False)
    monkeypatch.delenv("TALKBACK_FULL_MAX_CHARS", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    mod = _load()
    monkeypatch.setattr(mod, "SETTINGS", tmp_path / "settings.json")
    return mod


@pytest.fixture()
def spoken(hook, monkeypatch):
    """Capture what would have been spoken instead of speaking it."""
    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        hook, "speak_detached",
        lambda text, backend, output="": calls.append((text, backend, output)),
    )
    return calls


def _transcript(tmp_path: Path, session: str, text: str) -> Path:
    path = tmp_path / f"{session}.jsonl"
    path.write_text(
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
        + "\n"
    )
    return path


def _fire(hook, monkeypatch, payload: dict) -> int:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(sys, "argv", ["talkback-hook.py"])
    return hook.main()


def _stop_payload(tmp_path: Path, session: str, text: str = LONG_TURN) -> dict:
    return {
        "hook_event_name": "Stop",
        "session_id": session,
        "transcript_path": str(_transcript(tmp_path, session, text)),
    }


# --------------------------------------------------------------------------
# the isolation predicate — both polarities, same setup
# --------------------------------------------------------------------------

def test_session_that_opted_in_speaks(hook, tmp_path, monkeypatch, spoken):
    hook.write_config(hook.sessions_dir() / SESSION_A, {"mode": "always"})
    assert _fire(hook, monkeypatch, _stop_payload(tmp_path, SESSION_A)) == 0
    assert len(spoken) == 1
    assert LONG_TURN.startswith(spoken[0][0][:40])


def test_another_sessions_flag_leaves_this_session_silent(hook, tmp_path, monkeypatch, spoken):
    """The whole point: agent B talking must not make agent A audible."""
    hook.write_config(hook.sessions_dir() / SESSION_B, {"mode": "always"})
    assert _fire(hook, monkeypatch, _stop_payload(tmp_path, SESSION_A)) == 0
    assert spoken == []


def test_no_flag_anywhere_is_silent(hook, tmp_path, monkeypatch, spoken):
    assert _fire(hook, monkeypatch, _stop_payload(tmp_path, SESSION_A)) == 0
    assert spoken == []


def test_global_flag_speaks_for_any_session(hook, tmp_path, monkeypatch, spoken):
    hook.write_config(hook.global_flag(), {"mode": "always"})
    assert _fire(hook, monkeypatch, _stop_payload(tmp_path, SESSION_A)) == 0
    assert len(spoken) == 1


def test_session_mute_wins_over_the_global_flag(hook, tmp_path, monkeypatch, spoken):
    """`--off` in one session must silence it even while the machine flag is on."""
    hook.write_config(hook.global_flag(), {"mode": "always"})
    hook.write_config(hook.sessions_dir() / SESSION_A, {"mode": hook.MUTED})
    assert _fire(hook, monkeypatch, _stop_payload(tmp_path, SESSION_A)) == 0
    assert spoken == []
    # control: the untouched sibling session is still audible under the same flag
    assert _fire(hook, monkeypatch, _stop_payload(tmp_path, SESSION_B)) == 0
    assert len(spoken) == 1


def test_per_session_backend_is_honoured(hook, tmp_path, monkeypatch, spoken):
    hook.write_config(hook.sessions_dir() / SESSION_A, {"mode": "always", "backend": "elevenlabs"})
    _fire(hook, monkeypatch, _stop_payload(tmp_path, SESSION_A))
    assert spoken[0][1] == "elevenlabs"
    # control: the default is a *different* backend, so the assertion above is
    # reading the config and not a constant.
    hook.write_config(hook.sessions_dir() / SESSION_B, {"mode": "always"})
    _fire(hook, monkeypatch, _stop_payload(tmp_path, SESSION_B))
    assert spoken[1][1] == "elevenlabs"


def test_the_default_backend_is_the_top_of_the_ladder(hook, tmp_path, monkeypatch, spoken):
    """Talk mode asks for the best voice; talkback.py descends when it cannot."""
    hook.write_config(hook.sessions_dir() / SESSION_A, {"mode": "always"})
    _fire(hook, monkeypatch, _stop_payload(tmp_path, SESSION_A))
    assert spoken[0][1] == "elevenlabs"


def test_env_backend_overrides_the_default(hook, tmp_path, monkeypatch, spoken):
    monkeypatch.setenv("TALKBACK_HOOK_BACKEND", "say")
    hook.write_config(hook.sessions_dir() / SESSION_A, {"mode": "always"})
    _fire(hook, monkeypatch, _stop_payload(tmp_path, SESSION_A))
    assert spoken[0][1] == "say"


def test_per_session_output_routes_the_audio(hook, tmp_path, monkeypatch, spoken):
    """Two sessions on one host must be able to come out of two speakers."""
    hook.write_config(hook.sessions_dir() / SESSION_A, {"mode": "always", "output": "AirPods"})
    hook.write_config(hook.sessions_dir() / SESSION_B, {"mode": "always"})
    _fire(hook, monkeypatch, _stop_payload(tmp_path, SESSION_A))
    _fire(hook, monkeypatch, _stop_payload(tmp_path, SESSION_B))
    assert [c[2] for c in spoken] == ["AirPods", ""]


def test_env_output_overrides_the_stored_one(hook, tmp_path, monkeypatch, spoken):
    monkeypatch.setenv("TALKBACK_OUTPUT", "MacBook Pro Speakers")
    hook.write_config(hook.sessions_dir() / SESSION_A, {"mode": "always", "output": "AirPods"})
    _fire(hook, monkeypatch, _stop_payload(tmp_path, SESSION_A))
    assert spoken[0][2] == "MacBook Pro Speakers"


# --------------------------------------------------------------------------
# session identity
# --------------------------------------------------------------------------

def test_session_id_is_authoritative_over_a_disagreeing_transcript(hook):
    """A disagreement is not a reason to widen the search.

    This asserted `[SESSION_A, SESSION_B]` before BRO-2343: authorizing under
    both identities meant A could resolve B's flag.
    """
    keys = hook.payload_keys(
        {"session_id": SESSION_A, "transcript_path": f"/p/{SESSION_B}.jsonl"}
    )
    assert keys == [SESSION_A]


def test_a_forged_transcript_path_cannot_borrow_another_sessions_optin(
    hook, tmp_path, monkeypatch, spoken
):
    """The BLOCKER, end to end: B opted in, A did not, the payload names both."""
    hook.write_config(hook.sessions_dir() / SESSION_B, {"mode": "always"})
    payload = _stop_payload(tmp_path, SESSION_B)
    payload["session_id"] = SESSION_A          # the session actually running
    assert _fire(hook, monkeypatch, payload) == 0
    assert spoken == [], "session A spoke off session B's opt-in"


def test_transcript_stem_alone_resolves_the_session(hook, tmp_path, monkeypatch, spoken):
    """A payload without session_id must still find the flag, not fall silent."""
    hook.write_config(hook.sessions_dir() / SESSION_A, {"mode": "always"})
    payload = _stop_payload(tmp_path, SESSION_A)
    payload.pop("session_id")
    assert _fire(hook, monkeypatch, payload) == 0
    assert len(spoken) == 1


@pytest.mark.parametrize(
    "bad",
    ["../../etc/passwd", "a/b", "", "   ", ".hidden", "x" * 200, "a b"],
)
def test_unsafe_session_keys_are_rejected(hook, bad):
    assert hook.safe_key(bad) is None


def test_safe_session_key_survives(hook):
    assert hook.safe_key(SESSION_A) == SESSION_A


def test_traversal_key_cannot_reach_a_flag_outside_the_state_dir(hook, tmp_path, monkeypatch, spoken):
    # The decoy sits exactly where `sessions_dir() / "../outside/passwd"` lands,
    # so this fails the moment key hygiene stops rejecting the key. A decoy
    # anywhere else would pass against a hook with no hygiene at all.
    # `sessions/` must exist: the kernel resolves `sessions/../outside` component
    # by component, so a missing `sessions/` blocks the traversal on its own and
    # the test would pass against a hook with no key hygiene at all.
    hook.sessions_dir().mkdir(parents=True, exist_ok=True)
    decoy = hook.sessions_dir().parent / "outside" / "passwd"
    hook.write_config(decoy, {"mode": "always"})
    assert (hook.sessions_dir() / "../outside/passwd").resolve() == decoy.resolve()
    payload = {
        "hook_event_name": "Stop",
        "session_id": "../outside/passwd",
        "transcript_path": str(_transcript(tmp_path, SESSION_A, LONG_TURN)),
    }
    assert _fire(hook, monkeypatch, payload) == 0
    assert spoken == []


def test_cli_session_id_prefers_env(hook, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SESSION_A)
    assert hook.cli_session_id() == SESSION_A
    assert hook.cli_session_id(SESSION_B) == SESSION_B  # explicit still wins


def test_cli_refuses_to_guess_which_session_it_belongs_to(hook, monkeypatch):
    """No env, no --session: return None rather than pick a transcript.

    The removed fallback took the newest transcript in the cwd, so with two
    sessions open in one directory `--on` from A landed on B.
    """
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    assert hook.cli_session_id() is None
    assert not hasattr(hook, "newest_transcript_session")


def test_install_quotes_a_command_path_containing_a_space(hook, tmp_path, monkeypatch):
    """An install under "/…/skills copy/…" must not split into argv."""
    spaced = tmp_path / "skills copy" / "scripts"
    spaced.mkdir(parents=True)
    monkeypatch.setattr(hook, "HERE", spaced)
    assert hook.install() == 0
    settings = json.loads(hook.SETTINGS.read_text())
    cmds = [h["command"]
            for matchers in settings["hooks"].values()
            for m in matchers for h in m["hooks"]]
    assert cmds, "install registered nothing"
    for c in cmds:
        assert shlex.split(c) == [str(spaced / "talkback-hook.py")], c


# --------------------------------------------------------------------------
# lifecycle: SessionEnd + the idle janitor
# --------------------------------------------------------------------------

def test_session_end_removes_only_this_sessions_flag(hook, monkeypatch):
    hook.write_config(hook.sessions_dir() / SESSION_A, {"mode": "always"})
    hook.write_config(hook.sessions_dir() / SESSION_B, {"mode": "always"})
    payload = {"hook_event_name": "SessionEnd", "session_id": SESSION_A, "reason": "clear"}
    assert _fire(hook, monkeypatch, payload) == 0
    assert not (hook.sessions_dir() / SESSION_A).exists()
    assert (hook.sessions_dir() / SESSION_B).exists()


def test_prune_drops_idle_sessions_and_keeps_live_ones(hook):
    stale = hook.sessions_dir() / SESSION_A
    fresh = hook.sessions_dir() / SESSION_B
    hook.write_config(stale, {"mode": "always"})
    hook.write_config(fresh, {"mode": "always"})
    ancient = time.time() - (hook.TTL_HOURS + 1) * 3600
    os.utime(stale, (ancient, ancient))
    dropped = hook.prune_stale()
    assert dropped == [SESSION_A]
    assert fresh.exists()


def test_a_speaking_turn_keeps_the_session_alive(hook, tmp_path, monkeypatch, spoken):
    """The TTL is an idle timeout, not a lifetime cap on a long session."""
    flag = hook.sessions_dir() / SESSION_A
    hook.write_config(flag, {"mode": "always"})
    ancient = time.time() - (hook.TTL_HOURS + 1) * 3600
    os.utime(flag, (ancient, ancient))
    _fire(hook, monkeypatch, _stop_payload(tmp_path, SESSION_A))
    assert hook.prune_stale() == []
    assert flag.exists()


# --------------------------------------------------------------------------
# config reading
# --------------------------------------------------------------------------

@pytest.mark.parametrize("body,expected", [("marker", "marker"), ("always", "always"),
                                          ("full", "full"), ("brief", "brief"), ("off", "off")])
def test_legacy_bare_mode_body_still_reads(hook, body, expected):
    path = hook.sessions_dir() / SESSION_A
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body + "\n")
    assert hook.read_config(path) == {"mode": expected}


def test_empty_flag_file_takes_the_scope_default(hook):
    path = hook.sessions_dir() / SESSION_A
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    config, scope, _ = hook.resolve_state([SESSION_A])
    assert scope == "session"
    assert hook.effective_mode(config) == hook.SESSION_DEFAULT_MODE == "full"


def test_global_default_mode_is_the_quiet_one(hook):
    hook.global_flag().parent.mkdir(parents=True, exist_ok=True)
    hook.global_flag().write_text("")
    config, scope, _ = hook.resolve_state([SESSION_A])
    assert scope == "global"
    assert hook.effective_mode(config) == "marker"


def test_corrupt_flag_body_does_not_crash(hook):
    path = hook.sessions_dir() / SESSION_A
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    assert hook.read_config(path) == {}


# --------------------------------------------------------------------------
# what gets spoken
# --------------------------------------------------------------------------

LONG_BODY = (
    "Rewrote the resolver so the flag is keyed on the session id. "
    + "Then wired the SessionEnd cleanup behind it. " * 12
)


def test_full_speaks_the_whole_turn(hook):
    """The default is the answer, not a preview of it."""
    out = hook.readback(LONG_BODY, "full")
    assert out == LONG_BODY.strip()
    assert len(out) > hook.CAP  # the thing `brief` would have cut


def test_brief_cuts_where_full_does_not(hook):
    """Control for the test above: the ladder really has two rungs."""
    out = hook.readback(LONG_BODY, "brief")
    assert out is not None
    assert len(out) <= hook.CAP
    assert out != LONG_BODY.strip()


def test_full_has_no_floor(hook):
    """A short result is still a result when you are away from the screen."""
    assert hook.readback("Done, tests green.", "full") == "Done, tests green."
    assert hook.readback("Done, tests green.", "brief") is None


def test_full_leads_with_the_marker_then_gives_the_body(hook):
    text = LONG_BODY + "\n<!-- talkback: Keyed the flag on the session. -->"
    out = hook.readback(text, "full")
    assert out.startswith("Keyed the flag on the session.")
    assert LONG_BODY.strip() in out


def test_marker_mode_speaks_only_the_marker(hook):
    text = LONG_BODY + "\n<!-- talkback: Keyed the flag on the session. -->"
    assert hook.readback(text, "marker") == "Keyed the flag on the session."
    assert hook.readback(LONG_BODY, "marker") is None


def test_brief_prefers_the_marker_over_an_excerpt(hook):
    text = LONG_BODY + "\n<!-- talkback: Keyed the flag on the session. -->"
    assert hook.readback(text, "brief") == "Keyed the flag on the session."


def test_full_ceiling_is_off_unless_asked_for(hook, monkeypatch):
    monkeypatch.setenv("TALKBACK_FULL_MAX_CHARS", "120")
    capped = _load_with_env()
    out = capped.readback(LONG_BODY, "full")
    assert len(out) <= 120
    # control: the same body is uncapped in the default module
    assert len(hook.readback(LONG_BODY, "full")) > 120


def test_always_is_an_alias_for_full(hook):
    """0.3.0 flags say `always`; they must not silently become a preview."""
    assert hook.normalize_mode("always") == "full"
    assert hook.readback(LONG_BODY, hook.normalize_mode("always")) == LONG_BODY.strip()


def test_a_legacy_always_flag_speaks_in_full(hook, tmp_path, monkeypatch, spoken):
    hook.write_config(hook.sessions_dir() / SESSION_A, {"mode": "always"})
    _fire(hook, monkeypatch, _stop_payload(tmp_path, SESSION_A, LONG_BODY))
    assert spoken[0][0] == LONG_BODY.strip()


def test_unknown_mode_normalizes_to_nothing(hook):
    assert hook.normalize_mode("shouty") is None
    assert hook.normalize_mode("") is None
    assert hook.normalize_mode(None) is None


def test_muted_mode_never_produces_audio(hook, tmp_path, monkeypatch, spoken):
    hook.write_config(hook.sessions_dir() / SESSION_A, {"mode": hook.MUTED})
    _fire(hook, monkeypatch, _stop_payload(tmp_path, SESSION_A))
    assert spoken == []


# --------------------------------------------------------------------------
# it can never block a turn
# --------------------------------------------------------------------------

@pytest.mark.parametrize("raw", ["", "not json", "[]", "null", '{"session_id": 12}'])
def test_malformed_stdin_exits_zero(hook, monkeypatch, raw):
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    monkeypatch.setattr(sys, "argv", ["talkback-hook.py"])
    assert hook.main() == 0


def test_missing_transcript_exits_zero(hook, monkeypatch, spoken):
    hook.write_config(hook.sessions_dir() / SESSION_A, {"mode": "always"})
    payload = {
        "hook_event_name": "Stop",
        "session_id": SESSION_A,
        "transcript_path": "/nope/does-not-exist.jsonl",
    }
    assert _fire(hook, monkeypatch, payload) == 0
    assert spoken == []


def test_a_raising_speaker_still_exits_zero(hook, tmp_path, monkeypatch):
    hook.write_config(hook.sessions_dir() / SESSION_A, {"mode": "always"})

    def boom(text, backend, output=""):
        raise RuntimeError("no audio device")

    monkeypatch.setattr(hook, "speak_detached", boom)
    assert _fire(hook, monkeypatch, _stop_payload(tmp_path, SESSION_A)) == 0


# --------------------------------------------------------------------------
# toggle CLI
# --------------------------------------------------------------------------

def _run(hook, monkeypatch, argv: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", ["talkback-hook.py", *argv])
    monkeypatch.setattr(hook, "speak_detached", lambda text, backend, output="": None)
    return hook.main()


def test_on_defaults_to_full_detail_for_a_session(hook, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SESSION_A)
    assert _run(hook, monkeypatch, ["--on"]) == 0
    assert hook.read_config(hook.sessions_dir() / SESSION_A)["mode"] == "full"
    assert not hook.global_flag().exists()  # never writes the machine-wide flag


def test_on_global_defaults_to_marker_and_writes_the_global_flag(hook, monkeypatch):
    assert _run(hook, monkeypatch, ["--on", "--global"]) == 0
    assert hook.read_config(hook.global_flag())["mode"] == "marker"


def test_on_rejects_an_unknown_mode(hook, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SESSION_A)
    assert _run(hook, monkeypatch, ["--on", "shouty"]) == 2
    assert not (hook.sessions_dir() / SESSION_A).exists()


def test_on_accepts_a_backend_option_without_reading_it_as_the_mode(hook, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SESSION_A)
    assert _run(hook, monkeypatch, ["--on", "--backend", "elevenlabs"]) == 0
    config = hook.read_config(hook.sessions_dir() / SESSION_A)
    assert config["mode"] == "full"
    assert config["backend"] == "elevenlabs"


def test_on_accepts_an_explicit_detail_level(hook, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SESSION_A)
    assert _run(hook, monkeypatch, ["--on", "brief"]) == 0
    assert hook.read_config(hook.sessions_dir() / SESSION_A)["mode"] == "brief"


def test_on_stores_the_output_without_reading_it_as_the_mode(hook, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SESSION_A)
    assert _run(hook, monkeypatch, ["--on", "--output", "AirPods"]) == 0
    config = hook.read_config(hook.sessions_dir() / SESSION_A)
    assert config["mode"] == "full"
    assert config["output"] == "AirPods"


def test_off_removes_this_sessions_flag_only(hook, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SESSION_A)
    hook.write_config(hook.sessions_dir() / SESSION_A, {"mode": "always"})
    hook.write_config(hook.sessions_dir() / SESSION_B, {"mode": "always"})
    assert _run(hook, monkeypatch, ["--off"]) == 0
    assert not (hook.sessions_dir() / SESSION_A).exists()
    assert (hook.sessions_dir() / SESSION_B).exists()


def test_off_under_a_global_flag_writes_a_mute_rather_than_deleting(hook, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", SESSION_A)
    hook.write_config(hook.global_flag(), {"mode": "always"})
    hook.write_config(hook.sessions_dir() / SESSION_A, {"mode": "always"})
    assert _run(hook, monkeypatch, ["--off"]) == 0
    assert hook.read_config(hook.sessions_dir() / SESSION_A)["mode"] == hook.MUTED


def test_off_all_is_the_kill_switch(hook, monkeypatch):
    hook.write_config(hook.global_flag(), {"mode": "always"})
    hook.write_config(hook.sessions_dir() / SESSION_A, {"mode": "always"})
    hook.write_config(hook.sessions_dir() / SESSION_B, {"mode": "always"})
    assert _run(hook, monkeypatch, ["--off", "--all"]) == 0
    assert not hook.global_flag().exists()
    assert hook.enabled_sessions() == []


def test_on_without_a_resolvable_session_refuses(hook, monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "empty-home"))
    assert _run(hook, monkeypatch, ["--on"]) == 2


# --------------------------------------------------------------------------
# registration
# --------------------------------------------------------------------------

def test_install_registers_both_events_and_is_idempotent(hook, monkeypatch):
    hook.SETTINGS.write_text(json.dumps({"model": "opus", "hooks": {}}))
    assert _run(hook, monkeypatch, ["--install"]) == 0
    settings = json.loads(hook.SETTINGS.read_text())
    assert settings["model"] == "opus"  # unrelated settings survive
    assert hook._registered_events(settings) == {"Stop", "SessionEnd"}

    assert _run(hook, monkeypatch, ["--install"]) == 0
    settings2 = json.loads(hook.SETTINGS.read_text())
    assert settings2 == settings  # second run adds nothing


def test_install_dry_run_writes_nothing(hook, monkeypatch):
    hook.SETTINGS.write_text(json.dumps({"hooks": {}}))
    before = hook.SETTINGS.read_text()
    assert _run(hook, monkeypatch, ["--install", "--dry-run"]) == 0
    assert hook.SETTINGS.read_text() == before


def test_install_backs_the_settings_file_up(hook, monkeypatch, tmp_path):
    hook.SETTINGS.write_text(json.dumps({"hooks": {}, "keep": "me"}))
    _run(hook, monkeypatch, ["--install"])
    backups = list(tmp_path.glob("settings.json.talkback-bak-*"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text())["keep"] == "me"


def test_install_completes_a_partial_registration(hook, monkeypatch):
    """A pre-0.3.0 install has Stop only; SessionEnd must be added, once."""
    hook.SETTINGS.write_text(json.dumps({"hooks": {"Stop": [
        {"hooks": [{"type": "command", "command": "/x/talkback-hook.py"}]}
    ]}}))
    assert _run(hook, monkeypatch, ["--install"]) == 0
    settings = json.loads(hook.SETTINGS.read_text())
    assert hook._registered_events(settings) == {"Stop", "SessionEnd"}
    assert len(settings["hooks"]["Stop"]) == 1


def test_uninstall_removes_talkback_and_leaves_neighbours(hook, monkeypatch):
    hook.SETTINGS.write_text(json.dumps({"hooks": {"Stop": [
        {"hooks": [
            {"type": "command", "command": "/x/talkback-hook.py"},
            {"type": "command", "command": "/x/other-hook.sh"},
        ]}
    ]}}))
    assert _run(hook, monkeypatch, ["--uninstall"]) == 0
    settings = json.loads(hook.SETTINGS.read_text())
    commands = [
        h["command"] for m in settings["hooks"]["Stop"] for h in m["hooks"]
    ]
    assert commands == ["/x/other-hook.sh"]


# --------------------------------------------------------------------------
# the mid-session registration trap
# --------------------------------------------------------------------------

def _fake_session_transcript(hook, tmp_path, monkeypatch, session: str, when: float):
    home = tmp_path / "home"
    project = home / ".claude" / "projects" / "-w-proj"
    project.mkdir(parents=True, exist_ok=True)
    t = project / f"{session}.jsonl"
    t.write_text("{}\n")
    os.utime(t, (when, when))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return t


def test_a_hook_registered_after_the_session_started_is_flagged(hook, tmp_path, monkeypatch):
    """Claude Code snapshots hooks at session start; silence would look like a bug."""
    _fake_session_transcript(hook, tmp_path, monkeypatch, SESSION_A, when=1000.0)
    hook.install_marker().parent.mkdir(parents=True, exist_ok=True)
    hook.install_marker().write_text("2000.0\n")
    assert hook.registered_after_session_started(SESSION_A) is True


def test_a_hook_registered_before_the_session_is_not_flagged(hook, tmp_path, monkeypatch):
    """Control: same machinery, opposite order, must stay quiet."""
    _fake_session_transcript(hook, tmp_path, monkeypatch, SESSION_A, when=3000.0)
    hook.install_marker().parent.mkdir(parents=True, exist_ok=True)
    hook.install_marker().write_text("2000.0\n")
    assert hook.registered_after_session_started(SESSION_A) is False


def test_no_install_marker_never_guesses(hook, tmp_path, monkeypatch):
    """A pre-0.3.0 install has no marker; warning on a guess would be worse."""
    _fake_session_transcript(hook, tmp_path, monkeypatch, SESSION_A, when=1000.0)
    assert hook.registered_after_session_started(SESSION_A) is False
    assert hook.registered_after_session_started(None) is False


def test_install_records_when_it_registered(hook, monkeypatch):
    hook.SETTINGS.write_text(json.dumps({"hooks": {}}))
    assert _run(hook, monkeypatch, ["--install"]) == 0
    assert float(hook.install_marker().read_text().strip()) > 0
