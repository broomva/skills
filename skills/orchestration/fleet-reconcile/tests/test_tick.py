"""tick.sh end to end, and the CLI verbs around it, in an isolated HOME with
stub `claude`, `gh` and `maestro` that serve the captured fixture and
record how they were called (the fleet token's length only, never its value)."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from conftest import SCRIPTS, _git

TICK = SCRIPTS / "tick.sh"
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
    _stub(bin_ / "claude", 'echo "${#GH_TOKEN}" >> "%s/claude-token-lengths"\n'
          'case "$1" in\n'
          '  --version) cat "%s/claude/version.txt" ;;\n'
          '  agents) [ -n "${STUB_HANG:-}" ] && { (trap "" TERM; exec sleep 33) & wait; }; cat "%s/claude/agents.json" ;;\n'
          '  -p) env > "%s/coordinator-env"; printf "%%s\\n" "{\\"type\\": \\"system\\", \\"subtype\\": \\"init\\", '
          '\\"tools\\": [${STUB_TOOLS:-\\"Bash\\"}]}"; echo "{\\"type\\": \\"result\\"}" ;;\n'
          '  *) exit 2 ;;\nesac\n' % (calls_dir, fx, fx, calls_dir))
    _stub(bin_ / "gh", 'echo "${#GH_TOKEN}" >> "%s/gh-token-lengths"\n'
          'slug=""; for a in "$@"; do case "$a" in repos/*) slug=${a#repos/}; slug=${slug%%%%/rules*} ;; esac; done\n'
          'if [ "$1" = pr ]; then slug=$4; fi\n'
          'd="%s/gh/$(echo "$slug" | sed "s#/#__#")"\n'
          'case "$*" in\n'
          '  *rules/branches*) cat "$d/rules.json" ;;\n'
          '  *default_branch*) cat "$d/default_branch.txt" ;;\n'
          '  "pr list"*) cat "$d/prs.json" ;;\n'
          '  *) exit 1 ;;\nesac\n' % (calls_dir, fx))
    # maestro: `new` makes item itm-<n> (listed by `ls`); STUB_NEW_STATE sets its state, STUB_NEW_EXIT
    # makes `new` fail after creating it (Maestro creates, then dispatches); `show <id>` serves
    # calls/maestro-show-<id>.json, else review; `dispatch` starts it.
    _stub(bin_ / "maestro", '[ -n "${STUB_MAESTRO_DOWN:-}" ] && { echo "Maestro is not listening" >&2; exit 2; }\n'
          'printf "%%s\\n" "$*" | head -1 >> "%s/maestro"\n'
          '[ -n "${STUB_LOCK:-}" ] && [ -d "$STUB_LOCK" ] && echo held >> "%s/lock-during-alert"\n'
          'c="%s"\n'
          'case "$1" in\n'
          '  new) n=$(( $(cat "$c/maestro-n" 2>/dev/null || echo 0) + 1 )); echo $n > "$c/maestro-n";'
          ' printf "%%s\\n" "$*" > "$c/maestro-new-itm-$n";'
          ' title=$(printf "%%s" "$2" | tr -d \'"\'); init=""; prev=""; for a in "$@"; do [ "$prev" = --initiative ] && init=$a; prev=$a; done;'
          ' printf \'{"id": "itm-%%s", "title": "%%s", "initiative": "%%s", "state": "%%s"}\\n\' "$n" "$title" "$init"'
          ' "${STUB_NEW_STATE:-running}" >> "$c/maestro-items";'
          ' [ -n "${STUB_NEW_EXIT:-}" ] && { echo "Maestro gave no clear answer" >&2; exit "$STUB_NEW_EXIT"; };'
          ' echo "{\\"item\\": {\\"id\\": \\"itm-$n\\", \\"state\\": \\"${STUB_NEW_STATE:-running}\\"}}" ;;\n'
          '  ls) printf \'{"items": [\'; [ -f "$c/maestro-items" ] && paste -sd, "$c/maestro-items" | tr -d \'\\n\'; echo "]}" ;;\n'
          '  dispatch) echo "$2" >> "$c/maestro-dispatched"; echo "{\\"item\\": {\\"id\\": \\"$2\\", \\"state\\": \\"running\\"}}" ;;\n'
          '  show) f="$c/maestro-show-$2.json"; if [ -f "$f" ]; then cat "$f"; else'
          ' echo "{\\"item\\": {\\"state\\": \\"review\\", \\"verdict\\": null, \\"pending\\": null}, \\"events\\": []}"; fi ;;\n'
          '  *) exit 2 ;;\nesac\n' % (calls_dir, calls_dir, calls_dir))
    (w.home / ".claude" / "projects").mkdir(parents=True)
    shutil.copytree(str(fx / "claude" / "jobs"), str(w.home / ".claude" / "jobs"))
    shutil.copytree(str(fx / "paseo"), str(w.home / ".paseo"))
    _git("remote", "add", "origin", "https://github.com/broomva/workspace.git", cwd=w.home / "broomva")
    _git("remote", "add", "origin", "https://github.com/broomva/skills.git", cwd=w.home / "broomva" / "skills")
    tok = w.home / ".config" / "broomva" / "fleet" / "gh-token"
    tok.parent.mkdir(parents=True)
    tok.write_text(TOKEN + "\n")
    tok.chmod(0o600)
    env = {"FLEET_CLAUDE_BIN": str(bin_ / "claude"), "FLEET_GH_BIN": str(bin_ / "gh"),
           "CTX_CLAUDE_BIN": str(bin_ / "claude"), "FLEET_MAESTRO_BIN": str(bin_ / "maestro"),
           "FLEET_ASK_REPO": str(tmp_path / "ask-repo"), "FLEET_NOTIFY": "1", "FLEET_SCOPE": "broomva"}
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
            """Maestro's wire shape: the item's verdict, and the settled decision's event text and note."""
            words = {"approve": "You approved", "revise": "You sent it back", "block": "You canceled it"}
            ev = {"ts": "2026-10-01T12:00:00.000Z", "type": "gate.pending", "actor": "human",
                  "text": words.get(verdict, ""), "detail": note}
            (calls_dir / ("maestro-show-%s.json" % item)).write_text(json.dumps(
                {"item": {"state": state, "verdict": verdict if verdict in words else None, "pending": None},
                 "events": [ev] if verdict in words else []}))

        def brief(self, item):
            return (calls_dir / ("maestro-new-%s" % item)).read_text()

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
    # The owner channel is Paseo: one Maestro item at Needs you for the new batch, nothing on the desktop.
    assert "intent" in kinds and len(rig.raised("fleet broomva: ")) == 1, rig.calls("maestro")
    assert "--dispatch" in rig.brief("itm-1") and "--initiative fleet-reconcile-broomva" in rig.brief("itm-1")
    seen = [x for x in rig.ledger() if x["kind"] == "seen"]
    assert seen and seen[0]["result"] == {"channel": "maestro", "item": "itm-1", "state": "running"}
    assert kinds.index("seen") < kinds.index("runner_exit")  # inside the tick's lock now
    assert (sd / "asks" / "00001.md").is_file()


def test_the_fleet_token_reaches_gh_through_the_environment_and_nowhere_else(rig):
    rig.tick()
    lengths = set(rig.calls("gh-token-lengths"))
    assert lengths == {str(len(TOKEN))}
    assert set(rig.calls("claude-token-lengths")) == {"0"}  # claude runs without it
    sd = rig.world.state["broomva"]
    for p in sd.rglob("*"):
        if p.is_file():
            assert TOKEN not in p.read_text(errors="replace"), p
    assert "gh: fleet token file" in rig.log()


def test_without_a_token_file_gh_falls_back_to_the_keyring_and_the_report_says_so(rig):
    rig.token_file.unlink()
    rig.tick()
    assert set(rig.calls("gh-token-lengths")) == {"0"}
    assert "token file" in rig.log() and "unreadable" in rig.log()
    md = (rig.world.state["broomva"] / "ticks" / "00001" / "report.md").read_text()
    assert "read with the keyring token" in md


def test_an_empty_token_file_is_not_a_token(rig):
    rig.token_file.write_text("\n")
    rig.tick()
    assert set(rig.calls("gh-token-lengths")) == {"0"} and "is empty" in rig.log()


def test_a_token_file_open_to_others_is_not_used(rig):
    rig.token_file.chmod(0o644)
    rig.tick()
    assert set(rig.calls("gh-token-lengths")) == {"0"} and "not used" in rig.log()
    fire = [x for x in rig.ledger() if x["kind"] == "tick_fire"][0]
    assert "mode 644" in fire["detail"] and fire["detail"].startswith("release: checkout; gh: keyring")


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
    alerts = rig.raised("fleet broomva: tick-observe")
    assert len(alerts) == 1 and "failed at observe" in rig.brief("itm-%d" % len(rig.raised()))


def test_an_alert_maestro_didnt_take_is_raised_once_maestro_is_back(rig):
    sd = rig.world.state["broomva"]
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "ticks").write_text("a file where the ticks dir goes")  # observe fails every tick
    rig.tick(STUB_MAESTRO_DOWN="1")
    assert rig.raised("tick-observe") == [] and "NOT delivered" in rig.log()
    rig.tick()  # within the 6 h, but the first never reached the owner
    assert len(rig.raised("fleet broomva: tick-observe")) == 1
    rig.tick()
    assert len(rig.raised("fleet broomva: tick-observe")) == 1  # delivered: now rate-limited


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
    assert r.returncode == 1 and rig.raised("fleet broomva: tick") and "tick number" in rig.brief("itm-1")
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
    assert rig.raised("fleet broomva: lock") and "held for" in rig.brief("itm-1") and lock.exists()


def test_an_ask_maestro_doesnt_take_isnt_recorded_and_is_raised_at_the_next_tick(rig):
    r = rig.tick(STUB_MAESTRO_DOWN="1")
    assert r.returncode == 1
    assert not [x for x in rig.ledger() if x["kind"] == "seen"]
    assert "not raised" in rig.log() and "NOT delivered" in rig.log()  # the alert is logged, never a dialog
    rig.tick()
    assert [x for x in rig.ledger() if x["kind"] == "seen"] and rig.raised("fleet broomva: ")


def test_each_run_leaves_one_line_on_stdout_for_launchds_log(rig):
    r = rig.tick()
    lines = r.stdout.strip().splitlines()
    assert len(lines) == 1 and re.search(r"fleet-reconcile broomva tick 1: recover=0 observe=0 report=0 compare=\d ask=0$",
                                         lines[0]), r.stdout
    assert r.returncode == 0  # the core comparison's own verdict doesn't fail the tick


@pytest.mark.parametrize("cfg_dry,env_dry,expected", [(1, None, True), (0, None, False), (0, "1", True),
                                                      (1, "0", True), (0, "yes", True)])
def test_dry_run_falls_toward_dry(rig, cfg_dry, env_dry, expected):
    rig.world.write_config(dry_run=cfg_dry, gh_token_file=str(rig.token_file))
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


def test_a_batch_is_raised_once_and_the_owners_verdict_comes_back_as_the_answer(rig):
    rig.tick()
    rig.tick()
    assert len(rig.raised("fleet broomva: ")) == 1  # the item stays at Needs you; never raised twice
    assert len([x for x in rig.ledger() if x["kind"] == "seen"]) == 1  # nor looked up and re-recorded
    assert "[a1]" in rig.brief("itm-1") and "## Ask" in rig.brief("itm-1")
    rig.answer("itm-1", "revise", note="skills gets its pull_request rule this week")
    rig.tick()
    (ack,) = [x for x in rig.ledger() if x["kind"] == "ack" and x.get("by") == "owner:maestro"]
    batch = [x for x in rig.ledger() if x["kind"] == "intent" and x.get("verb") == "ask"][0]
    assert ack["of"] == batch["id"] and ack["asks"] == "all"
    assert ack["result"]["verdict"] == "revise" and ack["result"]["notes"][0].startswith("skills gets")
    assert "[tick 1, a1]" not in rig.fleet("asks").stdout


def test_a_canceled_item_dismisses_its_batch(rig):
    rig.tick()
    rig.answer("itm-1", "block", state="canceled")
    rig.tick()
    acks = [x for x in rig.ledger() if x["kind"] == "ack" and x.get("by") == "owner:maestro"]
    assert acks and acks[0]["result"]["verdict"] == "block"


def test_an_item_maestro_made_before_failing_is_adopted_not_raised_again(rig):
    r = rig.tick(STUB_NEW_EXIT="3")  # created, then "no clear answer"
    assert r.returncode == 1 and not [x for x in rig.ledger() if x["kind"] == "seen"]
    rig.tick()
    assert len(rig.raised("[batch ")) == 1  # found by its [batch ...] title, not created twice
    assert rig.raised("fleet broomva: tick-ask")  # the failed tick's own alert
    (seen,) = [x for x in rig.ledger() if x["kind"] == "seen"]
    assert seen["result"]["item"] == "itm-1"


def test_an_item_queued_at_maestros_cap_is_dispatched(rig):
    rig.tick(STUB_NEW_STATE="proposed")
    assert rig.calls("maestro-dispatched") == ["itm-1"]


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
    rig.world.write_config(mode="act", gh_token_file=str(rig.token_file))
    r = rig.tick()
    assert r.returncode == 0, rig.log()
    assert re.search(r"recover=0 observe=0 report=0 coordinator=0 compare=\d ask=0$", r.stdout.strip())
    sd = rig.world.state["broomva"]
    assert '"subtype": "init"' in (sd / "ticks" / "00001" / "coordinator.jsonl").read_text()
    hooks = json.loads((sd / "coordinator-settings.json").read_text())["hooks"]
    assert "send-gate pre --scope broomva" in hooks["PreToolUse"][0]["hooks"][0]["command"]
    env = dict(ln.split("=", 1) for ln in rig.calls("coordinator-env") if "=" in ln)
    assert env["FLEET_TICK"] == "1" and env["DRY_RUN"] == "1" and env["FLEET_CHILD"] == "1"
    assert len(env["GH_TOKEN"]) == len(TOKEN)  # the fleet token, for the coordinator's gh


def test_a_coordinator_with_a_disallowed_tool_is_stopped_and_the_tick_fails(rig):
    rig.world.write_config(mode="act")
    r = rig.tick(STUB_TOOLS='"Bash", "mcp__paseo__create_agent"')
    assert r.returncode == 1 and "coordinator=4" in r.stdout
    assert "Paseo write tool create_agent" in rig.log()
    assert rig.raised("fleet broomva: tick-coordinator")


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


def test_recover_reads_github_with_the_fleet_token(rig):
    sd = rig.world.state["broomva"]
    sd.mkdir(parents=True, exist_ok=True)
    rec = {"v": 1, "id": "0-1", "ts": "2026-09-30T00:00:00.000Z", "scope": "broomva", "tick": 0, "dry_run": False,
           "by": "act", "kind": "intent", "verb": "label", "key": "broomva/workspace#849",
           "target": {"repo": "broomva/workspace", "pr": 849, "label": "x", "op": "add"}}
    (sd / "ledger.jsonl").write_text(json.dumps(rec) + "\n")
    rig.tick()
    assert [x["by"] for x in rig.ledger() if x.get("of") == "0-1"] == ["recover"]
    assert set(rig.calls("gh-token-lengths")) == {str(len(TOKEN))}  # recover's gh call included


def test_a_live_tick_without_the_fleet_token_runs_no_coordinator_and_says_so(rig):
    rig.world.write_config(mode="act", dry_run=0)
    r = rig.tick()
    assert r.returncode == 1 and "coordinator=skipped" in r.stdout and rig.calls("coordinator-env") == []
    assert rig.raised("fleet broomva: tick-token")


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
