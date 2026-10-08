"""tick.sh end to end, and the CLI verbs around it, in an isolated HOME with
stub `claude`, `gh` and `maestro` that serve the captured fixture and
record how they were called (a token's length only, never its value)."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from conftest import SCRIPTS, _git
from fleetlib import common

TICK = SCRIPTS / "tick.sh"
BATCH = "[fleet-reconcile broomva batch "
TOKEN = "github_pat_" + "Z" * 40  # a fake, shaped like the real thing


def _stub(path: Path, body: str) -> Path:
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return path


@pytest.fixture
def rig(fresh_world, tmp_path):
    w = fresh_world
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    calls_dir = tmp_path / "calls"
    calls_dir.mkdir()
    fx = w.fixture
    _stub(bin_ / "claude", 'echo "${#GH_TOKEN}/${#GITHUB_TOKEN}" >> "%s/claude-token-lengths"\n'
          'case "$1" in\n'
          '  --version) cat "%s/claude/version.txt" ;;\n'
          '  agents) [ -n "${STUB_HANG:-}" ] && { (trap "" TERM; exec sleep 33) & wait; }; cat "%s/claude/agents.json" ;;\n'
          '  -p) env > "%s/coordinator-env"; printf "%%s\\n" "{\\"type\\": \\"system\\", \\"subtype\\": \\"init\\", '
          '\\"tools\\": [${STUB_TOOLS:-\\"Bash\\"}]}"; echo "{\\"type\\": \\"result\\"}" ;;\n'
          '  *) exit 2 ;;\nesac\n' % (calls_dir, fx, fx, calls_dir))
    _stub(bin_ / "gh", 'echo "${#GH_TOKEN}/${#GITHUB_TOKEN}" >> "%s/gh-token-lengths"\n'
          'slug=""; for a in "$@"; do case "$a" in repos/*) slug=${a#repos/}; slug=${slug%%%%/rules*} ;; esac; done\n'
          'if [ "$1" = pr ]; then slug=$4; fi\n'
          'd="%s/gh/$(echo "$slug" | sed "s#/#__#")"\n'
          'case "$*" in\n'
          '  *rules/branches*) cat "$d/rules.json" ;;\n'
          '  *default_branch*) cat "$d/default_branch.txt" ;;\n'
          '  "pr list"*) cat "$d/prs.json" ;;\n'
          '  *) exit 1 ;;\nesac\n' % (calls_dir, fx))
    # maestro: `new` makes item itm-<n> (listed by `ls`), queued, or with --dispatch (the bash fallback) in
    # STUB_NEW_STATE; STUB_NEW_EXIT makes `new` fail after creating it, saying STUB_NEW_ERR; STUB_NEW_HANG
    # makes it and a child ignore TERM and hang (STUB_NEW_ORPHAN: only the child); STUB_CLI_CRASH exits 1 as bun does when the CLI can't load,
    # before reaching Maestro; `show <id>` serves calls/maestro-show-<id>.json, else review; `dispatch`
    # starts it, or STUB_DISPATCH_EXIT refuses (the cap, or STUB_DISPATCH_ERR). Refusals read as bin/maestro.ts
    # prints them.
    _stub(bin_ / "maestro", '[ -n "${STUB_MAESTRO_DOWN:-}" ] && { echo "maestro: Maestro is not listening" >&2; exit 2; }\n'
          '[ -n "${STUB_CLI_CRASH:-}" ] && { echo "error: Module not found \\"maestro.ts\\"" >&2; exit 1; }\n'
          'printf "%%s\\n" "$*" | head -1 >> "%s/maestro"\n'
          'echo "${#GH_TOKEN}/${#GITHUB_TOKEN}" >> "%s/maestro-token-lengths"\n'
          '[ -n "${STUB_LOCK:-}" ] && [ -d "$STUB_LOCK" ] && echo held >> "%s/lock-during-alert"\n'
          'c="%s"\n'
          'case "$1" in\n'
          '  new) [ -n "${STUB_NEW_HANG:-}" ] && { trap "" TERM; sleep 60 & echo $! > "$c/hang-child"; wait; };'
          ' [ -n "${STUB_NEW_ORPHAN:-}" ] && { (trap "" TERM; exec sleep 60) & echo $! > "$c/hang-child"; sleep 60; };'
          ' n=$(( $(cat "$c/maestro-n" 2>/dev/null || echo 0) + 1 )); echo $n > "$c/maestro-n";'
          ' printf "%%s\\n" "$*" > "$c/maestro-new-itm-$n";'
          ' st=proposed; case " $* " in (*" --dispatch "*) st=${STUB_NEW_STATE:-running} ;; esac;'
          ' title=$(printf "%%s" "$2" | tr -d \'"\'); init=""; prev=""; for a in "$@"; do [ "$prev" = --initiative ] && init=$a; prev=$a; done;'
          ' printf \'{"id": "itm-%%s", "title": "%%s", "initiative": "%%s", "state": "%%s", "createdAt": "%%s"}\\n\''
          ' "$n" "$title" "$init" "$st" "$(date -u +%%FT%%TZ)" >> "$c/maestro-items";'
          ' [ -n "${STUB_NEW_EXIT:-}" ] && { echo "maestro: ${STUB_NEW_ERR:-Maestro gave no clear answer}" >&2; exit "$STUB_NEW_EXIT"; };'
          ' echo "{\\"item\\": {\\"id\\": \\"itm-$n\\", \\"state\\": \\"$st\\"}}" ;;\n'
          '  ls) printf \'{"items": [\'; [ -f "$c/maestro-items" ] && paste -sd, "$c/maestro-items" | tr -d \'\\n\'; echo "]}" ;;\n'
          '  dispatch) [ -n "${STUB_DISPATCH_EXIT:-}" ] && { echo "maestro: ${STUB_DISPATCH_ERR:-At capacity: 3 running. It stays queued.}" >&2; exit 1; };'
          ' echo "$2" >> "$c/maestro-dispatched"; echo "{\\"item\\": {\\"id\\": \\"$2\\", \\"state\\": \\"running\\"}}" ;;\n'
          '  show) f="$c/maestro-show-$2.json"; if [ -f "$f" ]; then cat "$f"; else'
          ' echo "{\\"item\\": {\\"state\\": \\"review\\", \\"verdict\\": null, \\"pending\\": null}, \\"events\\": []}"; fi ;;\n'
          '  *) exit 2 ;;\nesac\n' % (calls_dir, calls_dir, calls_dir, calls_dir))
    (w.home / ".claude" / "projects").mkdir(parents=True)
    shutil.copytree(str(fx / "claude" / "jobs"), str(w.home / ".claude" / "jobs"))
    shutil.copytree(str(fx / "paseo"), str(w.home / ".paseo"))
    _git("remote", "add", "origin", "https://github.com/broomva/workspace.git", cwd=w.home / "broomva")
    _git("remote", "add", "origin", "https://github.com/broomva/skills.git", cwd=w.home / "broomva" / "skills")
    tok = w.home / ".config" / "broomva" / "fleet" / "gh-token"
    tok.parent.mkdir(parents=True)
    tok.write_text(TOKEN + "\n")
    tok.chmod(0o600)
    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir()
    env = {"FLEET_CLAUDE_BIN": str(bin_ / "claude"), "FLEET_GH_BIN": str(bin_ / "gh"),
           "CTX_CLAUDE_BIN": str(bin_ / "claude"), "FLEET_MAESTRO_BIN": str(bin_ / "maestro"),
           "FLEET_ASK_REPO": str(tmp_path / "ask-repo"), "FLEET_NOTIFY": "1", "FLEET_SCOPE": "broomva",
           "TMPDIR": str(tmpdir)}  # isolate the TMPDIR alert-stamp fallback (broken state dir) per test
    base_config = w.write_config

    def write_config(**kw):
        kw.setdefault("ask_raise_after_min", 0)  # a batch reaches the owner at its own tick; the delay has its test
        return base_config(**kw)

    w.write_config = write_config
    w.write_config(gh_token_file=str(tok))

    class Rig:
        world, token_file = w, tok

        def tick(self, **extra: str) -> subprocess.CompletedProcess:
            e = dict(os.environ, **env)
            e.pop("CLAUDECODE", None)
            e.update(extra)
            return subprocess.run(["/bin/bash", str(TICK)], capture_output=True, text=True, env=e, timeout=180)

        def fleet(self, *args: str, **extra: str) -> subprocess.CompletedProcess:
            e = dict(env, CLAUDECODE="", FLEET_CHILD="")  # the owner's terminal, not a session
            e.update(extra)
            return w.fleet(*args, env=e)

        def ledger(self, scope="broomva"):
            p = w.state[scope] / "ledger.jsonl"
            return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []

        def log(self, scope="broomva"):
            p = w.state[scope] / "tick.log"
            return p.read_text() if p.exists() else ""

        def calls(self, name):
            p = calls_dir / name
            return p.read_text().splitlines() if p.exists() else []

        def raised(self, title_part=""):
            """The Maestro items raised (`new` calls), by title."""
            return [c for c in self.calls("maestro") if c.startswith("new ") and title_part in c]

        def answer(self, item, verdict="approve", note=None, state="done"):
            """Maestro's wire for a decision that took effect (server/events.ts toWireEvents): the
            settled decision's words and note, then "Took effect". The item's verdict is display text."""
            words = {"approve": "You approved", "revise": "You sent it back", "block": "You canceled it"}
            ev = {"ts": "2026-10-01T12:00:00.000Z", "type": "gate.pending", "actor": "human",
                  "text": words[verdict], "detail": note}
            took = dict(ev, type="gate", text="Took effect", detail=None)
            (calls_dir / ("maestro-show-%s.json" % item)).write_text(json.dumps(
                {"item": {"state": state, "verdict": words[verdict] if state in ("done", "canceled") else None,
                          "pending": None}, "events": [ev, took]}))

        def item(self, item, state, events=()):
            (calls_dir / ("maestro-show-%s.json" % item)).write_text(json.dumps(
                {"item": {"state": state, "verdict": None, "pending": None}, "events": list(events)}))

        def brief(self, item):
            return (calls_dir / ("maestro-new-%s" % item)).read_text()

        def asks(self, scope="broomva"):
            """The scope's ask ledger (fleetlib/ledger_ask.py): what Maestro's Decisions shows."""
            from fleetlib import ledger_ask
            return ledger_ask.read(w.state[scope] / ".control" / "asks" / ("fleet-%s.yaml" % scope))["asks"]

        def alerts(self, kind, scope="broomva"):
            return [a for a in self.asks(scope) if a.get("class") == "alert" and (a.get("fleet") or {}).get("alert") == kind]

        def answer_ask(self, uid, option, note="", scope="broomva"):
            """Maestro's answer, as its minimal edit writes it: `key: <JSON>` lines after the entry's id."""
            p = w.state[scope] / ".control" / "asks" / ("fleet-%s.yaml" % scope)
            lines = p.read_text().splitlines()
            at = next(i for i, ln in enumerate(lines) if ln == '  - id: "%s"' % uid)
            add = ['    answer_option: "%s"' % option, "    answer: %s" % json.dumps(note),
                   '    answered_at: "2026-10-08T12:00:00Z"', '    answered_by: "owner:maestro"', '    status: "resolved"']
            p.write_text("\n".join(lines[:at + 1] + add + lines[at + 1:]) + "\n")

    return Rig()


def test_a_tick_observes_reports_asks_and_records_itself(rig):
    r = rig.tick()
    assert r.returncode == 0, r.stderr
    sd = rig.world.state["broomva"]
    assert (sd / "tick-counter").read_text().strip() == "1"
    td = sd / "ticks" / "00001"
    for f in ("snapshot.json", "report.json", "report.md"):
        assert (td / f).is_file(), rig.log()
    kinds = [x["kind"] for x in rig.ledger()]
    assert kinds[0] == "tick_fire" and "runner_exit" in kinds
    assert [x for x in rig.ledger() if x["kind"] == "runner_exit"][0]["exit"] == 0, rig.log()
    assert all(x["by"] for x in rig.ledger()) and len({x["id"] for x in rig.ledger()}) == len(rig.ledger())
    rep = json.loads((td / "report.json").read_text())
    assert rep["surfaces"]["listing"]["ok"] and rep["dry_run"] is True
    assert any(a["key"].startswith("rules:broomva/skills") for a in rep["asks"])
    # The owner channel is the scope's ask ledger, answered in Maestro's Decisions (BRO-2908): no Maestro item,
    # no agent run, nothing on the desktop. A session waiting on the owner blocks; the rest do not.
    asks = rig.asks()
    assert "intent" in kinds and len(asks) == 4 and rig.raised() == [], rig.calls("maestro")
    waiting = [a for a in asks if a["fleet"]["ask"] == "a1"][0]
    assert waiting["headline"].startswith("Session interactive-session-47") and waiting["blocking"] is True
    assert [a["blocking"] for a in asks].count(True) == 1 and all(a["status"] is None for a in asks if "status" in a)
    assert (sd / "asks" / "00001.md").is_file()


def test_no_token_reaches_any_step_even_one_configured_or_inherited(rig, tmp_path):
    # Owner decision 2026-10-01: GitHub on the owner's gh login. gh_token_file is set (accepted, not read),
    # and a token inherited from the shell is dropped: by tick.sh for every step it starts (the Python every
    # step runs under is watched here), and by Sources for gh and every child.
    seen = tmp_path / "python-token-lengths"
    py = _stub(tmp_path / "python3", 'echo "$3 ${#GH_TOKEN}/${#GITHUB_TOKEN}" >> "%s"\nexec "%s" "$@"\n'
               % (seen, sys.executable))
    r = rig.tick(GH_TOKEN=TOKEN, GITHUB_TOKEN=TOKEN, FLEET_PYTHON=str(py))
    assert r.returncode == 0, rig.log()
    assert set(rig.calls("gh-token-lengths")) == {"0/0"} and set(rig.calls("claude-token-lengths")) == {"0/0"}
    steps = [ln.split() for ln in seen.read_text().splitlines()]
    assert {"config-get", "config-check", "recover", "observe", "report", "act"} <= {cmd for cmd, _ in steps}
    assert {n for _, n in steps} == {"0/0"}  # every one, the config reads before the lock included
    sd = rig.world.state["broomva"]
    for p in sd.rglob("*"):
        if p.is_file():
            assert TOKEN not in p.read_text(errors="replace"), p
    assert "gh: keyring (the owner's gh login)" in rig.log()


def test_no_inherited_token_reaches_the_bash_alert_fallback(rig):
    rig.world.config.write_text("not json")  # the fallback runs before anything else does
    rig.tick(GH_TOKEN=TOKEN, GITHUB_TOKEN=TOKEN)
    assert rig.raised("fleet broomva: config") and set(rig.calls("maestro-token-lengths")) == {"0/0"}


def test_the_kill_switch_stops_the_tick_before_anything_fires(rig):
    rig.world.write_config(dispatch_enabled=0)
    rig.tick()
    rig.tick()
    sd = rig.world.state["broomva"]
    assert not (sd / "tick-counter").exists() and rig.ledger() == []
    assert rig.calls("gh-token-lengths") == [] and rig.calls("maestro") == []
    assert rig.log().count("DISABLED") == 1  # noted once, not every hour


@pytest.mark.parametrize("bad", ["not json", json.dumps({"v": 1, "scopes": {"broomva": {"dispatch_enabled": 1,
                                                                                         "surprise": 1}}})])
def test_an_unreadable_or_invalid_config_stops_the_tick_and_alerts_once(rig, bad):
    rig.world.config.write_text(bad)
    first, second = rig.tick(), rig.tick()
    assert first.returncode == 1 and second.returncode == 1
    assert rig.ledger() == [] and rig.calls("gh-token-lengths") == []
    assert len(rig.raised("fleet broomva: config")) == 1  # at most once per 6 h per kind


def test_a_failed_step_alerts_and_exits_1(rig):
    sd = rig.world.state["broomva"]
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "ticks").write_text("a file where the ticks dir goes")  # observe can't write its snapshot
    r = rig.tick()
    assert r.returncode == 1
    assert [x for x in rig.ledger() if x["kind"] == "runner_exit"][0]["exit"] == 1
    (alert,) = rig.alerts("tick-observe")
    assert "failed at observe" in alert["headline"] and alert["blocking"] is True and rig.raised() == []


def test_an_alert_is_written_once_per_six_hours_refreshed_while_open_and_new_once_answered(rig):
    sd = rig.world.state["broomva"]
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "ticks").write_text("a file where the ticks dir goes")  # observe fails every tick
    rig.tick()
    rig.tick()  # within the 6 h: not written again
    assert len(rig.alerts("tick-observe")) == 1
    (sd / ".alert-tick-observe").unlink()  # as if 6 h had passed: the open one is refreshed, not doubled
    rig.tick()
    (alert,) = rig.alerts("tick-observe")
    rig.answer_ask(alert["uid"], "ack")
    (sd / ".alert-tick-observe").unlink()
    time.sleep(1.1)  # a new alert's uid carries the second it was raised
    rig.tick()
    assert len(rig.alerts("tick-observe")) == 2 and rig.raised() == []


def test_a_lost_counter_does_not_reuse_a_tick_number(rig):
    rig.tick()
    rig.tick()
    (rig.world.state["broomva"] / "tick-counter").unlink()
    rig.tick()
    fires = [x["tick"] for x in rig.ledger() if x["kind"] == "tick_fire"]
    assert fires == [1, 2, 3]


def test_no_tick_number_releases_the_lock_before_the_alert(rig):
    sd = rig.world.state["broomva"]
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "tick-counter").mkdir()  # next-tick can't write its counter
    r = rig.tick(STUB_LOCK=str(sd / ".tick.lock"))
    (alert,) = rig.alerts("tick")
    assert r.returncode == 1 and "tick number" in alert["headline"]
    assert rig.calls("lock-during-alert") == [] and not (sd / ".tick.lock").exists()


def test_a_lock_held_past_two_hours_alerts_the_owner(rig):
    sd = rig.world.state["broomva"]
    sd.mkdir(parents=True, exist_ok=True)
    lock = sd / ".tick.lock"
    lock.mkdir()
    (lock / "pid").write_text(str(os.getpid()))  # alive: not reclaimed
    old = time.time() - 3 * 3600
    os.utime(lock, (old, old))
    assert rig.tick().returncode == 1
    (alert,) = rig.alerts("lock")
    assert "held for" in alert["headline"] and lock.exists()


def test_each_run_leaves_one_line_on_stdout_for_launchds_log(rig):
    r = rig.tick()
    lines = r.stdout.strip().splitlines()
    assert len(lines) == 1 and re.search(r"fleet-reconcile broomva tick 1: recover=0 observe=0 report=0 compare=\d ask=0$",
                                         lines[0]), r.stdout
    assert r.returncode == 0  # the core comparison's own verdict doesn't fail the tick


@pytest.mark.parametrize("cfg_dry,env_dry,expected", [(1, None, True), (0, None, False), (0, "1", True),
                                                      (1, "0", True), (0, "yes", True)])
def test_dry_run_falls_toward_dry(rig, cfg_dry, env_dry, expected):
    rig.world.write_config(dry_run=cfg_dry,
                           **({"live_accepted": "phase 3, BRO-2755 and BRO-2756 done (test)"} if cfg_dry == 0 else {}))
    rig.tick(**({"DRY_RUN": env_dry} if env_dry is not None else {}))
    fire = [x for x in rig.ledger() if x["kind"] == "tick_fire"][0]
    assert fire["dry_run"] is expected


def test_a_live_lock_skips_the_tick_and_a_stale_one_is_reclaimed(rig):
    sd = rig.world.state["broomva"]
    sd.mkdir(parents=True, exist_ok=True)
    lock = sd / ".tick.lock"
    lock.mkdir()
    (lock / "pid").write_text(str(os.getpid()))  # this test process: alive
    rig.tick()
    assert "holds the lock" in rig.log() and not (sd / "tick-counter").exists()
    dead = subprocess.Popen(["true"])
    dead.wait()
    (lock / "pid").write_text(str(dead.pid))
    old = time.time() - 600
    os.utime(lock, (old, old))
    rig.tick()
    assert "reclaimed a stale lock" in rig.log() and (sd / "tick-counter").read_text().strip() == "1"
    assert not lock.exists()


def test_a_reclaim_in_progress_keeps_a_second_tick_out(rig):
    sd = rig.world.state["broomva"]
    sd.mkdir(parents=True, exist_ok=True)
    lock = sd / ".tick.lock"
    lock.mkdir()
    old = time.time() - 600
    os.utime(lock, (old, old))  # stale: no pid, old
    (sd / ".tick.lock.reclaim").mkdir()  # another tick is reclaiming it right now
    assert rig.tick().returncode == 0
    assert not (sd / "tick-counter").exists() and lock.exists()


def test_the_kill_switch_off_is_not_a_failure(rig):
    rig.world.write_config(dispatch_enabled=0)
    assert rig.tick().returncode == 0 and rig.calls("maestro") == []


def test_the_recursion_guard_exits_before_anything(rig):
    rig.tick(FLEET_CHILD="1")
    assert rig.ledger() == [] and rig.log() == ""


def test_a_hung_step_is_stopped_by_the_watchdog_children_included(rig):
    t0 = time.monotonic()
    r = rig.tick(FLEET_TICK_TIMEOUT_S="3", STUB_HANG="1")
    assert time.monotonic() - t0 < 25 and r.returncode == 1
    assert "over the tick's budget: sent TERM to its process group" in rig.log()
    assert [x for x in rig.ledger() if x["kind"] == "runner_exit"][0]["exit"] == 1
    assert not (rig.world.state["broomva"] / ".tick.lock").exists()
    time.sleep(0.5)
    left = subprocess.run(["pgrep", "-f", "sleep 33"], capture_output=True, text=True).stdout.split()
    assert left == [], "the hung stub's child outlived the tick"


def test_each_ask_is_one_ledger_entry_and_the_owners_answer_comes_back_once(rig):
    rig.tick()
    rig.tick()
    asks = rig.asks()
    assert len(asks) == 4 and len({a["uid"] for a in asks}) == 4  # one entry per ask, never written twice
    a1 = [a for a in asks if a["fleet"]["ask"] == "a1"][0]
    assert a1["fleet"]["class"] == "7" and [o["id"] for o in a1["options"]] == ["ack", "dismiss"]
    rig.answer_ask(a1["uid"], "ack", note="skills gets its pull_request rule this week")
    rig.tick()
    rig.tick()  # read back once
    (ack,) = [x for x in rig.ledger() if x["kind"] == "ack" and x.get("by") == "owner:maestro"]
    batch = [x for x in rig.ledger() if x["kind"] == "intent" and x.get("verb") == "ask"][0]
    assert ack["of"] == batch["id"] and ack["asks"] == ["a1"]
    assert ack["result"]["option"] == "ack" and ack["result"]["answer"].startswith("skills gets")
    assert "[tick 1, a1]" not in rig.fleet("asks").stdout


def test_dismissing_an_ask_answers_it(rig):
    rig.tick()
    a1 = [a for a in rig.asks() if a["fleet"]["ask"] == "a1"][0]
    rig.answer_ask(a1["uid"], "dismiss")
    rig.tick()
    acks = [x for x in rig.ledger() if x["kind"] == "ack" and x.get("by") == "owner:maestro"]
    assert acks and acks[0]["result"]["option"] == "dismiss" and acks[0]["asks"] == ["a1"]


def test_an_ask_reaches_the_ledger_only_once_it_has_lasted(rig):
    rig.world.write_config(ask_raise_after_min=50)
    r = rig.tick()
    assert r.returncode == 0 and rig.asks() == [] and "4 waiting" in rig.log()
    # An hour on, the asks are still open: they are written.
    lines = (rig.world.state["broomva"] / "ledger.jsonl").read_text().splitlines()
    old = common.ts(time.time() - 3600)
    (rig.world.state["broomva"] / "ledger.jsonl").write_text("\n".join(
        json.dumps(dict(json.loads(x), ts=old)) for x in lines) + "\n")
    rig.tick()
    assert len(rig.asks()) == 4


@pytest.mark.parametrize("extra", [{"STUB_NEW_STATE": "proposed"}, {"STUB_NEW_EXIT": "3"},
                                   # made, then its run couldn't start: Maestro refuses, and the item exists
                                   {"STUB_NEW_EXIT": "1", "STUB_NEW_ERR": "Could not start the run: no provider"}])
def test_the_bash_fallback_raises_at_most_one_alert_per_6_h_even_queued_or_unconfirmed(rig, extra):
    # It can't adopt an open item or read Maestro's words, so any answer counts (else one more every tick).
    rig.world.config.write_text("not json")
    rig.tick(**extra)
    rig.tick(**extra)
    sd = rig.world.state["broomva"]
    assert len(rig.raised("fleet broomva: config [fleet-reconcile broomva alert config]")) == 1
    assert (sd / ".alert-config").exists()


@pytest.mark.parametrize("down, code", [("STUB_MAESTRO_DOWN", 2),  # not listening
                                        ("STUB_CLI_CRASH", 1)])   # bun's own exit 1, no "maestro: " line
def test_the_bash_fallback_tries_again_when_nothing_reached_maestro(rig, down, code):
    rig.world.config.write_text("not json")
    rig.tick(**{down: "1"})  # nothing was sent, so nothing was made
    sd = rig.world.state["broomva"]
    assert not (sd / ".alert-config").exists() and "NOT delivered" in rig.log()
    assert "no answer from Maestro (exit %d)" % code in rig.log()
    rig.tick()
    assert len(rig.raised("fleet broomva: config")) == 1 and (sd / ".alert-config").exists()


def test_a_bash_fallback_whose_maestro_hangs_is_stopped_children_and_all(rig):
    rig.world.config.write_text("not json")
    t0 = time.monotonic()
    r = rig.tick(STUB_NEW_HANG="1", FLEET_ALERT_TIMEOUT_S="1", FLEET_KILL_GRACE_S="1")  # both ignore TERM
    assert r.returncode == 1 and time.monotonic() - t0 < 30
    assert "(exit 137)" in rig.log() and not (rig.world.state["broomva"] / ".alert-config").exists()
    child = int(rig.calls("hang-child")[0])
    time.sleep(0.5)
    with pytest.raises(ProcessLookupError):
        os.kill(child, 0)  # the group was killed, not only its leader


def test_a_bash_fallback_whose_leader_dies_still_has_its_term_proof_child_killed(rig):
    rig.world.config.write_text("not json")
    rig.tick(STUB_NEW_ORPHAN="1", FLEET_ALERT_TIMEOUT_S="1", FLEET_KILL_GRACE_S="20")  # the leader dies on TERM
    assert "(exit 143)" in rig.log()
    child = int(rig.calls("hang-child")[0])
    time.sleep(0.5)
    with pytest.raises(ProcessLookupError):
        os.kill(child, 0)  # killed with its group once the leader was reaped, not left for its 60 s


def test_the_bash_fallback_reaches_maestro_when_its_state_dir_is_broken(rig):
    rig.world.config.write_text("not json")
    sd = rig.world.state["broomva"]
    sd.parent.mkdir(parents=True, exist_ok=True)
    sd.write_text("a file where the state dir goes")  # nothing can be written there, the log included
    r = rig.tick()
    assert r.returncode == 1 and len(rig.raised("fleet broomva: config")) == 1  # the last channel still works


def test_an_unwritable_state_dir_alerts_its_own_kind_not_a_config_failure(rig):
    # A valid config but a state dir that can't be written: the owner hears the real reason (statedir), once,
    # not a misread config-check every hour (#263 review). The stamp lives under TMPDIR (writable).
    sd = rig.world.state["broomva"]
    sd.parent.mkdir(parents=True, exist_ok=True)
    sd.write_text("a file where the state dir goes")
    r1 = rig.tick()
    r2 = rig.tick()
    assert r1.returncode == 1 and r2.returncode == 1
    assert len(rig.raised("fleet broomva: statedir")) == 1  # its own kind, deduped via the TMPDIR stamp
    assert not rig.raised("fleet broomva: config")  # not misread as a config-check failure


def test_the_bash_fallback_classifies_by_exit_code_when_mktemp_fails(rig, tmp_path):
    # mktemp can't make its temp file: run without capturing (no command substitution that could hang on
    # an escaped Maestro child — P20 round 2) and classify by exit code, so an ambiguous exit 1 is stamped,
    # not retried every tick the way a /dev/null it can't grep would be (#263 review).
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(0o500)  # read+execute, no write: mktemp fails here
    rig.world.config.write_text("not json")  # force the bash fallback
    sd = rig.world.state["broomva"]
    r = rig.tick(TMPDIR=str(ro), STUB_NEW_EXIT="1")  # Maestro exits 1
    assert r.returncode == 1 and (sd / ".alert-config").exists()  # classified as answered -> stamped, not retried
    assert "no answer from Maestro" not in rig.log() and "by code alone" in rig.log()


def test_live_mode_is_refused_until_its_preconditions_are_recorded(rig):
    # 0.4.0 removed the token that kept live mode closed; dry_run 0 alone no longer makes a tick live.
    rig.world.write_config(mode="act", dry_run=0)
    check = rig.fleet("config-check", "broomva")
    assert check.returncode == 1 and "live_accepted" in check.stderr
    r = rig.tick()
    assert r.returncode == 1 and rig.alerts("config") and rig.calls("coordinator-env") == []
    assert not [x for x in rig.ledger() if x["kind"] == "tick_fire"]  # no tick at all
    # A note that doesn't name both gate tickets is still refused (#263 review: no bare "no"/"TODO").
    rig.world.write_config(mode="act", dry_run=0, live_accepted="BRO-2755 done, 2756 TODO")
    check = rig.fleet("config-check", "broomva")
    assert check.returncode == 1 and "BRO-2756" in check.stderr
    rig.world.write_config(mode="act", dry_run=0, live_accepted="phase 3, BRO-2755 and BRO-2756 done (test)")
    assert rig.fleet("config-check", "broomva").returncode == 0


def test_every_verb_stays_dry_while_live_mode_is_unaccepted(rig):
    import argparse

    import fleet_reconcile
    args = argparse.Namespace(dry_run=None)
    gate = "phase 3, BRO-2755 and BRO-2756 done"
    assert fleet_reconcile._dry(args, {"scope": "broomva", "dry_run": 0}) is True            # not set
    assert fleet_reconcile._dry(args, {"scope": "broomva", "dry_run": 0, "live_accepted": " "}) is True   # blank
    assert fleet_reconcile._dry(args, {"scope": "broomva", "dry_run": 0, "live_accepted": "done"}) is True  # no ticket
    assert fleet_reconcile._dry(args, {"scope": "broomva", "dry_run": 0, "live_accepted": "BRO-2755"}) is True  # one
    assert fleet_reconcile._dry(args, {"scope": "broomva", "dry_run": 0,
                                       "live_accepted": "BRO-27550 BRO-27560"}) is True  # substrings, not the ids
    assert fleet_reconcile._dry(args, {"scope": "broomva", "dry_run": 0, "live_accepted": gate}) is False  # both named
    assert fleet_reconcile._dry(args, {"scope": "broomva", "dry_run": 1, "live_accepted": gate}) is True   # dry_run 1


def test_every_verb_stays_dry_at_the_cli_under_an_unaccepted_dry_run_0(rig):
    # Not just _dry(): the dryness flows through the actual verbs (#263 review). dry_run 0 with no live_accepted.
    rig.world.write_config(mode="act", dry_run=0)
    assert rig.fleet("is-dry").stdout.strip() == "1"  # the one source of truth tick.sh reads
    lab = rig.fleet("act", "label", "--repo", "broomva/workspace", "--pr", "849", "--label", "ci-heal-escalation")
    res = json.loads(lab.stdout)
    assert res["dry_run"] is True and res["result"]["would"] is True  # label logs only
    assert "acting dry" in lab.stderr and "live_accepted" in lab.stderr  # #3: it says why
    sp = rig.fleet("act", "spawn", "--repo", "broomva/workspace", "--pr", "849")
    assert "acting dry" in sp.stderr  # printed before spawn runs, whatever it then decides
    (rig.world.state["broomva"] / "ticks" / "00001").mkdir(parents=True, exist_ok=True)  # the report step makes this
    rig.fleet("coordinator", "--scope", "broomva", "--tick", "1")  # config-check would block a full tick; call direct
    env = dict(ln.split("=", 1) for ln in rig.calls("coordinator-env") if "=" in ln)
    assert env["DRY_RUN"] == "1"  # the coordinator child is told dry even though dry_run is 0


def test_the_owner_reads_and_acks_asks_and_other_verbs_refuse(rig):
    rig.tick()
    asks = rig.fleet("asks")
    assert asks.returncode == 0
    assert "[tick 1, a1]" in asks.stdout
    assert rig.fleet("ack", "1", "--ask", "zz").returncode == 1
    inside = rig.fleet("ack", "1", CLAUDECODE="1")
    assert inside.returncode == 3 and "refused" in inside.stderr  # a floor: an owner step, from a terminal
    acked = rig.fleet("ack", "1")
    assert acked.returncode == 0 and re.search(r"[1-9]\d* open ask\(s\) answered in 1 batch", acked.stdout)
    again = rig.fleet("ack", "1")
    assert again.returncode == 0 and "0 open ask(s)" in again.stdout and "nothing there was open" in again.stdout
    assert "no open asks" in rig.fleet("asks").stdout
    assert any(x["kind"] == "ack" for x in rig.ledger())
    for verb in ("mail", "spawn", "label", "resume"):
        out = rig.fleet("act", verb)
        assert out.returncode == 3 and "refused" in out.stderr


def test_a_failed_compare_does_not_use_up_the_day_and_the_prototypes_line_is_refused(rig):
    rig.world.write_config(compare_hour=0)
    path = rig.world.home / ".local" / "state" / "ctx" / "broomva" / "compare.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))  # noqa: E731
    reg = ts(time.time() - 40 * 3600)
    proto = {"ts": ts(time.time() - 30 * 3600), "registered": reg, "pass": True}
    path.write_text(json.dumps(proto) + "\n")
    out = rig.fleet("core-compare")
    assert out.returncode == 0 and "not run (prototype)" in out.stdout
    rig.tick()  # the report says so and asks the owner
    rep = json.loads((rig.world.state["broomva"] / "ticks" / "00001" / "report.json").read_text())
    assert "compare:move" in [a["key"] for a in rep["asks"]] and rep["core_compare"] == {"refused": "prototype"}
    path.write_text(json.dumps(dict(proto, neither=0)) + "\n"
                    + json.dumps({"ts": ts(time.time()), "registered": reg, "pass": False,
                                  "error": "CompareError: claude agents exited 1"}) + "\n")
    out = rig.fleet("core-compare")
    assert "not due" not in out.stdout, out.stdout + out.stderr
    assert len(path.read_text().splitlines()) == 3  # it ran, and wrote its line


def test_in_act_mode_the_tick_recovers_then_runs_the_coordinator_with_the_send_gate(rig):
    rig.world.write_config(mode="act")
    r = rig.tick()
    assert r.returncode == 0, rig.log()
    assert re.search(r"recover=0 observe=0 report=0 coordinator=0 compare=\d ask=0$", r.stdout.strip())
    sd = rig.world.state["broomva"]
    assert '"subtype": "init"' in (sd / "ticks" / "00001" / "coordinator.jsonl").read_text()
    hooks = json.loads((sd / "coordinator-settings.json").read_text())["hooks"]
    assert "send-gate pre --scope broomva" in hooks["PreToolUse"][0]["hooks"][0]["command"]
    env = dict(ln.split("=", 1) for ln in rig.calls("coordinator-env") if "=" in ln)
    assert env["FLEET_TICK"] == "1" and env["DRY_RUN"] == "1" and env["FLEET_CHILD"] == "1"
    assert "GH_TOKEN" not in env  # the coordinator's gh uses the owner's login


def test_a_coordinator_with_a_disallowed_tool_is_stopped_and_the_tick_fails(rig):
    rig.world.write_config(mode="act")
    r = rig.tick(STUB_TOOLS='"Bash", "mcp__paseo__create_agent"')
    assert r.returncode == 1 and "coordinator=4" in r.stdout
    assert "Paseo write tool create_agent" in rig.log()
    assert rig.alerts("tick-coordinator")


def test_a_tick_first_closes_the_intents_a_dead_tick_left_open(rig):
    sd = rig.world.state["broomva"]
    sd.mkdir(parents=True, exist_ok=True)
    rec = {"v": 1, "id": "0-1", "ts": "2026-09-30T00:00:00.000Z", "scope": "broomva", "tick": 0, "dry_run": True,
           "by": "act", "kind": "intent", "verb": "spawn", "key": "broomva-x-pr1", "target": {"name": "broomva-x-pr1"}}
    (sd / "ledger.jsonl").write_text(json.dumps(rec) + "\n")
    rig.tick()
    out = [x for x in rig.ledger() if x.get("of") == "0-1"]
    assert len(out) == 1 and out[0]["kind"] == "failed" and out[0]["by"] == "recover" and out[0]["tick"] == 1
    assert "recover: 0-1 spawn broomva-x-pr1 -> failed" in rig.log()


def test_recover_reads_github_on_the_owners_login(rig):
    sd = rig.world.state["broomva"]
    sd.mkdir(parents=True, exist_ok=True)
    rec = {"v": 1, "id": "0-1", "ts": "2026-09-30T00:00:00.000Z", "scope": "broomva", "tick": 0, "dry_run": False,
           "by": "act", "kind": "intent", "verb": "label", "key": "broomva/workspace#849",
           "target": {"repo": "broomva/workspace", "pr": 849, "label": "x", "op": "add"}}
    (sd / "ledger.jsonl").write_text(json.dumps(rec) + "\n")
    rig.tick()
    assert [x["by"] for x in rig.ledger() if x.get("of") == "0-1"] == ["recover"]
    assert set(rig.calls("gh-token-lengths")) == {"0/0"}  # recover's gh call included: no token


def test_a_live_tick_runs_the_coordinator_on_the_owners_login(rig):
    # The fleet token is waived (spec §5.2 precondition 1): a live tick needs none.
    rig.world.write_config(mode="act", dry_run=0, live_accepted="phase 3, BRO-2755 and BRO-2756 done (test)")
    r = rig.tick()
    assert r.returncode == 0 and "coordinator=0" in r.stdout and rig.calls("coordinator-env") != [], rig.log()
    assert not rig.raised("tick-token")


def test_in_report_mode_no_coordinator_runs(rig):
    rig.tick()
    assert rig.calls("coordinator-env") == [] and "coordinator=" not in rig.log()


def test_three_ticks_make_a_labelling_sheet(rig):
    for _ in range(3):
        rig.tick()
    out = rig.fleet("label-sheet", "--ticks", "1,2,3")
    assert out.returncode == 0, out.stderr
    md, csv_ = out.stdout.split()
    assert Path(md).is_file() and Path(csv_).read_text().startswith("row,tick,session")
