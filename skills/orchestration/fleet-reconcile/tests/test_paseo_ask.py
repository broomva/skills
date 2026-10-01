"""The owner channel on Paseo (owner decision 2026-10-01): asks as Maestro work
at Needs you, and the owner's verdict read back. maestro here is a stub."""
from __future__ import annotations

import json
import os

import pytest

from fleetlib import config, paseo_ask


@pytest.fixture
def stub(world, tmp_path, monkeypatch):
    out = tmp_path / "show.json"
    log = tmp_path / "args"
    bin_ = tmp_path / "maestro"
    bin_.write_text('#!/bin/sh\nprintf "%%s\\n" "$@" > "%s"\n[ -n "$STUB_EXIT" ] && { echo nope >&2; exit $STUB_EXIT; }\n'
                    'case "$1" in new) echo \'{"item": {"id": "w1", "state": "running"}}\' ;; '
                    'show) cat "%s" ;; esac\n' % (log, out))
    bin_.chmod(0o755)
    monkeypatch.setenv("FLEET_MAESTRO_BIN", str(bin_))
    world.write_config(ask_repo=str(tmp_path / "asks-repo"))
    return type("S", (), {"sec": config.scope("broomva"), "show": out, "args": log})


def test_raising_dispatches_work_in_the_fleets_own_repo(stub):
    item = paseo_ask.raise_item(stub.sec, "fleet broomva: 2 asks (tick 3)",
                                paseo_ask.brief("broomva", "lead", ["[a1] q one", "[a2] q two"], "approve"))
    args = stub.args.read_text().splitlines()
    assert item["id"] == "w1" and args[0] == "new" and "--dispatch" in args and args[-1] == "--json"
    repo = args[args.index("--repo") + 1]
    assert os.path.isdir(os.path.join(repo, ".git")) and args[args.index("--initiative") + 1] == "fleet-reconcile-broomva"
    text = args[args.index("--brief") + 1:]
    assert "- [a1] q one" in text and "Change nothing and run no tools." in " ".join(text)


@pytest.mark.parametrize("events, state, want", [
    ([], "review", (None, None)),
    ([{"type": "gate", "actor": "human", "verdict": "approve", "note": None, "ts": "t1"}], "done", ("approve", None)),
    ([{"type": "gate", "actor": "human", "verdict": "revise", "note": "yes, do it", "ts": "t1"}], "running",
     ("revise", "yes, do it")),
    ([{"type": "gate", "actor": "agent", "verdict": "approve"}], "review", (None, None)),  # only the owner's counts
    ([], "canceled", ("cancel", None)),
])
def test_the_owners_verdict_is_read_back(stub, events, state, want):
    stub.show.write_text(json.dumps({"item": {"state": state, "updatedAt": "t2"}, "events": events}))
    ans = paseo_ask.answer(stub.sec, "w1")
    assert (ans["verdict"], ans["note"]) == want and ans["state"] == state


def test_a_note_passes_the_text_guard(stub):
    stub.show.write_text(json.dumps({"item": {"state": "running"}, "events": [
        {"type": "gate", "actor": "human", "verdict": "revise", "note": "token ghp_" + "x" * 36, "ts": "t"}]}))
    assert paseo_ask.answer(stub.sec, "w1")["note"] == "[withheld]"


@pytest.mark.parametrize("code, why", [(1, "refused"), (2, "not listening"), (3, "no clear answer")])
def test_maestros_failures_are_errors_with_their_meaning(stub, monkeypatch, code, why):
    monkeypatch.setenv("STUB_EXIT", str(code))
    with pytest.raises(paseo_ask.MaestroError) as exc:
        paseo_ask.answer(stub.sec, "w1")
    assert exc.value.code == code and why in str(exc.value)
