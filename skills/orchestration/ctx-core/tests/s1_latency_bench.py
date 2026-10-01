#!/usr/bin/env python3
"""Wall-clock latency of the System 1 hook, the way Claude Code runs it.

    python3 tests/s1_latency_bench.py --home H --workspace W --params P [-n 200]

Each run is `/bin/sh ctx-s1-hook.sh <stage>` with the payload on stdin, timed
from outside the process: shell, interpreter start-up, imports, the decision,
the state write, the log line and the exit. Per stage it reports p50 / p90 / p99
/ max with the stage off (flags unset: one /bin/sh) and on, and the floor of a
bare `python3 -I -S -c pass`, so the gate's share can be read off. H is a HOME
whose ~/.config/ctx/scopes.yaml scopes W and whose cache `ctx-s1 build` has
built; the benchmark writes decisions and session state there, never to the
real HOME unless H is it. Not run in CI: CI runners start Python slower than
the owner's machine, and a p99 on a shared runner measures the runner.
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def payload(stage, i, ws):
    base = {"session_id": "bench-%s-%d" % (stage, i // 5), "cwd": ws, "transcript_path": "/dev/null"}
    if stage == "prompt":
        base.update(hook_event_name="UserPromptSubmit",
                    prompt="is the higgsfield api cheaper than the subscription for video generation %d" % i)
    elif stage == "pre-edit":
        base.update(hook_event_name="PreToolUse", tool_name="Edit",
                    tool_input={"file_path": ws + "/docs/specs/x.html", "old_string": "x" * 2000, "new_string": "y"})
    elif stage == "post-read":
        base.update(hook_event_name="PostToolUse", tool_name="Read", tool_input={"file_path": ws + "/README.md"},
                    tool_response={"type": "text", "file": {"content": "z" * 20000}})
    elif stage == "post-bash":
        cmds = ["git status", "ls -la", "sed -n 1,40p README.md", "git push -u origin HEAD"]
        base.update(hook_event_name="PostToolUse", tool_name="Bash", tool_input={"command": cmds[i % 4]},
                    tool_response={"stdout": "ok\n" * 200})
    elif stage in ("session-start", "compact"):
        base.update(hook_event_name="SessionStart", source="startup" if stage == "session-start" else "compact")
    elif stage == "subagent":
        base.update(hook_event_name="SubagentStart", agent_id="a%d" % i, agent_type="general-purpose")
    return json.dumps(base).encode()


def pct(ts):
    ts = sorted(ts)
    n = len(ts)
    return {"p50": round(statistics.median(ts), 1), "p90": round(ts[max(0, int(0.9 * n) - 1)], 1),
            "p99": round(ts[max(0, int(0.99 * n) - 1)], 1), "max": round(ts[-1], 1), "n": n}


def run(argv, env, data):
    t = time.perf_counter()
    subprocess.run(argv, input=data, capture_output=True, env=env)
    return (time.perf_counter() - t) * 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True)
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--params", required=True)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("-n", type=int, default=200)
    a = ap.parse_args()
    base = {"HOME": a.home, "PATH": "/usr/bin:/bin", "CTX_PYTHON": a.python, "CTX_S1_PARAMS": a.params}
    wrapper = str(SCRIPTS / "ctx-s1-hook.sh")
    out = {"load_average": os.getloadavg(), "python": a.python}
    out["floor_python"] = pct([run([a.python, "-I", "-S", "-c", "pass"], base, b"") for _ in range(a.n)])
    for stage in ("pre-edit", "post-read", "post-bash", "prompt", "session-start", "compact", "subagent"):
        off = [run(["/bin/sh", wrapper, stage], base, payload(stage, i, a.workspace)) for i in range(a.n)]
        on_env = dict(base, CTX_S1="1", CTX_S1_STAGES=stage)
        on = [run(["/bin/sh", wrapper, stage], on_env, payload(stage, i, a.workspace)) for i in range(a.n)]
        out[stage] = {"off": pct(off), "on": pct(on)}
        print(stage, out[stage], flush=True)
    out["load_average_after"] = os.getloadavg()
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
