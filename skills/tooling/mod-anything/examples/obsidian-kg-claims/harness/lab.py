#!/usr/bin/env python3
"""lab.py — the scriptable runtime for the KG Claims mod: launch, act, wait, capture.

Drives the real Obsidian app in a lab, never the user's profile or vault:

  setup   <lab> --entities DIR --slugs type/slug ...  build <lab>/vault from the fixtures and
                                                      copies of the named entity files, and a
                                                      lab profile at <lab>/obsidian-data
  launch  <lab>                                       start Obsidian in the background on the lab
                                                      profile; record its PID in <lab>/pid
  cli     <lab> ARG ...                               run Obsidian's own CLI against the lab instance
  install <lab>                                       copy ../plugin into the lab vault
  stop    <lab>                                       stop the recorded PID (exact PID only)

The order for a run is in ../INSTALL.txt (section "Re-run the lab").

Why each lab knob exists (all observed on Obsidian 1.13.7, macOS 26.5):
- --user-data-dir: Obsidian honours it; the profile, vault registry (obsidian.json) and
  localStorage (restricted-mode consent) all live there.
- HOME=<lab>/home: the 1.12+ CLI server binds os.homedir()/.obsidian-cli.sock on every start,
  unlinking whatever is there. With the real HOME, a lab instance would take over the user's
  CLI socket. A lab HOME keeps the socket in the lab.
- --use-mock-keychain: Chromium's switch for a mock keychain. Obsidian 1.13.7 writes a
  keychain item at startup. With the lab HOME there is no login keychain, so the main thread
  blocks in a login-keychain authorization prompt, and every IPC channel (single-instance
  socket, CLI socket, DevTools port) hangs behind it. On the real HOME it would touch the
  user's login keychain. The mock avoids both.
- "cli": true in the lab obsidian.json: the same switch as Settings > General > Advanced >
  Command line interface; without it the server answers every command with a refusal.
- defaultViewMode "preview" in the lab vault's app.json: notes open in reading view.

Pure stdlib. macOS only (uses `open` and the app bundle path).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

APP = Path("/Applications/Obsidian.app")
EXE = APP / "Contents" / "MacOS" / "Obsidian"
HERE = Path(__file__).resolve().parent
PLUGIN_SRC = HERE.parent / "plugin"
FIXTURES = HERE / "fixtures"
VAULT_ID = "6d6f646c61623031"
PLUGIN_ID = "kg-claims"
LAUNCHER_LINE = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d ")


def paths(lab: Path) -> dict[str, Path]:
    return {"vault": lab / "vault", "data": lab / "obsidian-data", "home": lab / "home",
            "pid": lab / "pid", "stdout": lab / "obsidian.stdout", "stderr": lab / "obsidian.stderr"}


def cmd_setup(lab: Path, entities: Path, slugs: list[str]) -> None:
    p = paths(lab)
    if p["vault"].exists() and any(p["vault"].iterdir()):
        raise SystemExit(f"refused: {p['vault']} is not empty")
    shutil.copytree(FIXTURES / "vault", p["vault"], dirs_exist_ok=True)
    for slug in slugs:
        src = entities / f"{slug}.md"
        dst = p["vault"] / "entities" / f"{slug}.md"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)  # a copy: the real entity is only ever read
    cfg = p["vault"] / ".obsidian"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "app.json").write_text(json.dumps({"defaultViewMode": "preview"}) + "\n")
    p["data"].mkdir(parents=True, exist_ok=True)
    p["home"].mkdir(parents=True, exist_ok=True)
    reg = {"vaults": {VAULT_ID: {"path": str(p["vault"]), "ts": int(time.time() * 1000), "open": True}},
           "cli": True}
    (p["data"] / "obsidian.json").write_text(json.dumps(reg) + "\n")
    print(f"lab ready: {lab}")


def _main_pids(lab: Path) -> list[int]:
    out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout
    # The main instance, not a CLI client: only the main carries --enable-logging=stderr.
    want = f"{EXE} --user-data-dir={paths(lab)['data']} --use-mock-keychain --enable-logging=stderr"
    return [int(line.split(None, 1)[0]) for line in out.splitlines()
            if line.split(None, 1)[1:] and line.split(None, 1)[1].startswith(want)]


def _open(lab: Path) -> None:
    p = paths(lab)
    if _main_pids(lab):
        raise SystemExit(f"refused: a lab instance is already running: {_main_pids(lab)}")
    # open -g: launch without bringing the app forward; -n: a new instance, never the user's.
    subprocess.run(["open", "-g", "-n", "-a", str(APP), "--env", f"HOME={p['home']}",
                    "--stdout", str(p["stdout"]), "--stderr", str(p["stderr"]),
                    "--args", f"--user-data-dir={p['data']}", "--use-mock-keychain", "--enable-logging=stderr"],
                   check=True)


def _wait_pid(lab: Path, until, wait: float) -> int:
    deadline = time.time() + wait
    while time.time() < deadline:
        pids = _main_pids(lab)
        if pids:
            paths(lab)["pid"].write_text(f"{pids[0]}\n")
            if until():
                return pids[0]
        time.sleep(0.5)
    raise SystemExit("timed out waiting for the lab instance")


def cmd_launch(lab: Path, wait: float = 60.0) -> int:
    p = paths(lab)
    if not list(p["data"].glob("obsidian-*.asar")):
        # A fresh profile runs the installer's bundled app code (1.8.4 here, no CLI) and the
        # launcher downloads the current release into the profile. Warm up once, then relaunch.
        _open(lab)
        _wait_pid(lab, lambda: bool(list(p["data"].glob("obsidian-*.asar"))), wait)
        cmd_stop(lab)
    sock = p["home"] / ".obsidian-cli.sock"
    if sock.exists():
        sock.unlink()  # our own lab socket from the last run; the new instance binds a fresh one
    _open(lab)
    # The 1.12+ app code binds its CLI socket early in every start: a readiness signal.
    pid = _wait_pid(lab, sock.exists, wait)
    print(f"launched pid {pid}")
    return pid


def cli(lab: Path, args: list[str], timeout: float = 20.0) -> str:
    """Obsidian's own CLI: a second Obsidian process that hands its argv to the lab instance
    over <lab>/home/.obsidian-cli.sock and prints the answer. On a timeout, stop that client
    by its exact PID, never by name."""
    p = paths(lab)
    env = dict(os.environ, HOME=str(p["home"]))
    proc = subprocess.Popen([str(EXE), f"--user-data-dir={p['data']}", "--use-mock-keychain", *args],
                            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise SystemExit(f"cli {' '.join(args)}: no answer in {timeout:.0f} s (client pid {proc.pid} stopped)")
    # The client prints the launcher's log line first; the answer follows it.
    lines = [ln for ln in out.splitlines()
             if not LAUNCHER_LINE.match(ln) and not ln.startswith("Your Obsidian installer is out of date")]
    return "\n".join(lines).strip()



def cmd_install(lab: Path) -> None:
    dst = paths(lab)["vault"] / ".obsidian" / "plugins" / PLUGIN_ID
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("manifest.json", "main.js", "styles.css"):
        shutil.copyfile(PLUGIN_SRC / name, dst / name)
    print(f"installed into lab vault: {dst}")



def cmd_stop(lab: Path) -> None:
    p = paths(lab)
    if not p["pid"].exists():
        print("no pid recorded")
        return
    pid = int(p["pid"].read_text().strip())
    if pid not in _main_pids(lab):
        print(f"pid {pid} is not a lab instance any more; nothing to stop")
        return
    # The exact PID we started, never a pattern. On macOS the first SIGTERM can close the
    # window and leave the app running windowless (seen once in 4 stops); a second SIGTERM
    # to the same PID quits it. A main thread blocked in a system prompt needs SIGKILL,
    # which this does not send on its own.
    for attempt in (1, 2):
        os.kill(pid, 15)
        for _ in range(40):
            if pid not in _main_pids(lab):
                print(f"stopped pid {pid} (SIGTERM x{attempt})")
                return
            time.sleep(0.25)
    raise SystemExit(f"pid {pid} did not exit after two SIGTERMs; sample it before anything else")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lab.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup"); s.add_argument("lab"); s.add_argument("--entities", required=True)
    s.add_argument("--slugs", nargs="+", required=True)
    sub.add_parser("launch").add_argument("lab")
    k = sub.add_parser("cli"); k.add_argument("lab"); k.add_argument("args", nargs=argparse.REMAINDER)
    for name in ("install", "stop"):
        sub.add_parser(name).add_argument("lab")
    ns = ap.parse_args(argv)
    lab = Path(os.path.abspath(ns.lab))  # not resolve(): keep /tmp as given, the PID match uses it
    if ns.cmd == "setup":
        cmd_setup(lab, Path(ns.entities).expanduser(), ns.slugs)
    elif ns.cmd == "launch":
        cmd_launch(lab)
    elif ns.cmd == "install":
        cmd_install(lab)
    elif ns.cmd == "cli":
        print(cli(lab, ns.args))
    elif ns.cmd == "stop":
        cmd_stop(lab)
    return 0


if __name__ == "__main__":
    sys.exit(main())
